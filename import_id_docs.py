import os
import sqlite3
import re
import cv2
import pytesseract
import fitz  # PyMuPDF לטיפול ישיר וקל בקבצי PDF
import numpy as np

# הגדרת נתיב ברירת המחדל למידת הצורך (שנה אם מותקן במיקום אחר)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(img):
    """עיבוד מקדים של תמונה קיימת בזיכרון לשיפור דיוק ה-OCR"""
    if img is None:
        return None
    # הפיכה לגווני אפור
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # הגדלת הניגודיות (בינאריזציה)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return thresh

def extract_numbers_from_pdf(pdf_path):
    """חילוץ מספרים ישירות מתוך קובץ PDF ללא תלות ב-OpenCV"""
    numbers = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            # שלב א' - ניסיון לחלץ טקסט ישיר (אם ה-PDF נוצר מאקסל או וורד ולא מסריקה)
            text = page.get_text()
            found = re.findall(r'\b\d{5,9}\b', text)
            numbers.extend(found)
            
            # שלב ב' - אם לא נמצא טקסט, נמיר את העמוד לתמונה בזיכרון ונפעיל OCR
            if not found:
                pix = page.get_pixmap(dpi=200)
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.h, pix.w, pix.n))
                processed = preprocess_image(img_data)
                text_ocr = pytesseract.image_to_string(processed, config='--psm 11')
                numbers.extend(re.findall(r'\b\d{5,9}\b', text_ocr))
        doc.close()
    except Exception as e:
        print(f"שגיאה בעיבוד קובץ PDF: {e}")
    return numbers

def extract_numbers_from_image(image_path):
    """חילוץ מספרים מקובץ תמונה (JPG/PNG) תוך עקיפת בעיית הקידוד של נתיבים בעברית"""
    try:
        # קריאת הקובץ כמערך בייטים כדי למנוע קריסה בשמות עם עברית
        with open(image_path, "rb") as f:
            chunk = f.read()
        chunk_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(chunk_arr, cv2.IMREAD_COLOR)
        
        processed_img = preprocess_image(img)
        if processed_img is None:
            return []
        
        text = pytesseract.image_to_string(processed_img, config='--psm 11')
        return re.findall(r'\b\d{5,9}\b', text)
    except Exception as e:
        return []

def process_id_folder():
    db_path = "students.db"
    source_folder = "source_id_photos" 
    target_folder = os.path.join("uploads", "id_photos")
    
    if not os.path.exists(source_folder):
        print(f"אנא צור תיקייה בשם '{source_folder}' ושים בה את הצילומים.")
        return

    os.makedirs(target_folder, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    matched_count = 0

    print("מתחיל בסריקת מסמכים חכמה וחילוץ נתונים...")
    
    # שימוש ב-os.scandir לטיפול אמין יותר בשמות קבצים בעברית
    with os.scandir(source_folder) as entries:
        for entry in entries:
            if not entry.is_file() or not entry.name.lower().endswith(('.png', '.jpg', '.jpeg', '.pdf')):
                continue
                
            filename = entry.name
            file_path = entry.path
            
            # זיהוי סוג הקובץ והפעלת פונקציית החילוץ המתאימה
            if filename.lower().endswith('.pdf'):
                extracted_digits = extract_numbers_from_pdf(file_path)
            else:
                extracted_digits = extract_numbers_from_image(file_path)
            
            found_match = False
            # ניקוי וסינון כפילויות ברשימת המספרים שנמצאו
            unique_candidates = list(set(extracted_digits))
            
            for digit_candidate in unique_candidates:
                clean_digits = digit_candidate.strip()
                
                # אם המספר קצר מ-9 ספרות (למשל 8 ספרות), נבדוק גם גרסה מרופדת ב-0 בהתחלה
                candidates_to_check = [clean_digits]
                if len(clean_digits) < 9:
                    candidates_to_check.append(clean_digits.zfill(9))
                
                for current_tz in candidates_to_check:
                    cursor.execute("SELECT id, tz FROM students WHERE tz = ?", (current_tz,))
                    student = cursor.fetchone()
                    
                    if student:
                        student_id, tz = student
                        
                        # יצירת שם קובץ תקני והעברתו לתיקיית היעד
                        new_filename = f"id_{tz}_{filename}"
                        dest_path = os.path.join(target_folder, new_filename)
                        
                        try:
                            # סגירת משאבים והעברה בטוחה
                            if os.path.exists(dest_path):
                                os.remove(dest_path)
                            os.replace(file_path, dest_path)
                            
                            db_save_path = f"/uploads/id_photos/{new_filename}"
                            cursor.execute("""
                                UPDATE students 
                                SET id_photo_path = ?, id_photo_exists = 1 
                                WHERE id = ?
                            """, (db_save_path, student_id))
                            
                            print(f"✓ נמצאה התאמה לתלמיד עם זיהוי {tz}. הקובץ שויך: {filename}")
                            found_match = True
                            matched_count += 1
                            break
                        except Exception as file_err:
                            print(f"שגיאה בהעברת הקובץ {filename}: {file_err}")
                
                if found_match:
                    break
                    
            if not found_match:
                print(f"?- לא נמצא תלמיד מתאים עבור הקובץ: {filename} (מספרים שזוהו בתוכו: {unique_candidates})")

    conn.commit()
    conn.close()
    print(f"\nהתהליך הסתיים. שויכו בהצלחה {matched_count} מסמכי זיהוי לתלמידים.")

if __name__ == "__main__":
    process_id_folder()