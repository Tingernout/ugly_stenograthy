import cv2
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
from crypto_lsb import encrypt_message, decrypt_message, embed_bit, extract_bit


def d2xy(n, d):
    # Перевод номера точки d в координаты x,y кривой Гильберта порядка n
    # Реализация из Википедии https://en.wikipedia.org/wiki/Hilbert_curve
    x = 0
    y = 0
    t = d
    s = 1
    for i in range(n):
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return x, y


def hilbert_curve_points(order):
    # Возвращает список координат (x,y) точек по кривой Гильберта порядка order
    n = 2 ** order
    total_points = n * n
    points = [d2xy(order, d) for d in range(total_points)]
    return points


def ism_image(input_image, text, password=None):
    """Шифрует и записывает текст в изображение по кривой Гильберта используя LSB."""
    if not os.path.exists(input_image):
        return False, "Файл не найден."
    
    isnachal_photo = cv2.imread(input_image)
    if isnachal_photo is None:
        return False, "Ошибка: невозможно загрузить изображение. Проверьте путь и формат файла."

    height, width, _ = isnachal_photo.shape
    
    # Определяем максимальный порядок кривой Гильберта, который помещается в изображение
    max_order = 0
    for order in range(3, 8):  # от 3 до 7
        min_dim = 2 ** order
        if height >= min_dim and width >= min_dim * 4:
            max_order = order
        else:
            break
    
    if max_order < 3:
        return False, "Изображение слишком маленькое для кривой Гильберта (минимум 8x32 пикселей)."
    
    points = hilbert_curve_points(max_order)
    modify_image = isnachal_photo.copy()

    # Если пароль предоставлен, шифруем текст
    if password:
        binary_payload = encrypt_message(password, text)
    else:
        # Без пароля просто конвертируем текст в биты (не рекомендуется для безопасности)
        binary_payload = ''.join(format(ord(c), '08b') for c in text)
    
    # Добавляем префикс с длиной данных (32 бита)
    length_prefix = format(len(binary_payload), '032b')
    full_payload = length_prefix + binary_payload
    
    # Проверяем, что изображение вмещает все биты
    max_capacity = len(points) * 3  # 3 канала на пиксель
    if len(full_payload) > max_capacity:
        return False, f"Текст слишком большой для этого изображения. Максимум бит: {max_capacity} (порядок {max_order}), требуется: {len(full_payload)}. Попробуйте изображение большего размера."

    # Внедряем биты в LSB каналов пикселей
    bit_index = 0
    for (x, y) in points:
        px_x = x * 4
        if px_x >= width or y >= height:
            break
        
        try:
            pixel = modify_image[y, px_x].copy()
            for channel in range(3):
                if bit_index >= len(full_payload):
                    break
                pixel[channel] = embed_bit(pixel[channel], full_payload[bit_index])
                bit_index += 1
            modify_image[y, px_x] = pixel
            
            if bit_index >= len(full_payload):
                break
        except (IndexError, ValueError) as e:
            return False, f"Ошибка при записи бита {bit_index}: {e}"

    if bit_index < len(full_payload):
        return False, f"Не удалось записать все данные. Записано: {bit_index} из {len(full_payload)} бит."

    output_path = "modify_image.png"
    try:
        cv2.imwrite(output_path, modify_image)
        return True, f"Текст успешно зашифрован и записан в изображение (LSB, порядок {max_order}). Сохранен как {output_path}."
    except Exception as e:
        return False, f"Ошибка при сохранении файла: {e}"


def image_looking(input_image, password=None):
    """Извлекает и расшифровывает текст из изображения по кривой Гильберта."""
    if not os.path.exists(input_image):
        return False, "Файл не найден."
    
    modify_image = cv2.imread(input_image)
    if modify_image is None:
        return False, "Ошибка: невозможно загрузить изображение. Проверьте путь и формат файла."

    height, width, _ = modify_image.shape

    # Определяем максимальный порядок кривой Гильберта
    max_order = 0
    for order in range(3, 8):
        min_dim = 2 ** order
        if height >= min_dim and width >= min_dim * 4:
            max_order = order
        else:
            break
    
    if max_order < 3:
        return False, "Изображение слишком маленькое для кривой Гильберта."
    
    points = hilbert_curve_points(max_order)

    # Извлекаем биты из LSB каналов пикселей
    extracted_bits = ""
    max_bits = len(points) * 3  # 3 канала на пиксель (BGR)
    
    for (x, y) in points:
        px_x = x * 4
        if y >= height or px_x >= width:
            break
        try:
            pixel = modify_image[y, px_x]
            # Извлекаем биты из каждого канала (B, G, R)
            for channel in range(3):
                extracted_bits += extract_bit(pixel[channel])
                if len(extracted_bits) >= max_bits:
                    break
        except (IndexError, ValueError):
            continue
    
    # Читаем длину данных из первых 32 бит
    if len(extracted_bits) < 32:
        return False, "Недостаточно данных для чтения длины."
    
    data_length = int(extracted_bits[:32], 2)
    data_bits = extracted_bits[32:32+data_length]
    
    if len(data_bits) < data_length:
        return False, f"Недостаточно данных. Ожидалось: {data_length}, получено: {len(data_bits)}"
    
    # Если пароль предоставлен, пытаемся расшифровать
    if password:
        try:
            decrypted_text = decrypt_message(password, data_bits)
            return True, decrypted_text
        except Exception as e:
            return False, f"Ошибка расшифровки: неверный пароль или повреждённые данные. ({e})"
    else:
        # Без пароля возвращаем сырые биты (для отладки)
        return True, f"Извлечено бит: {len(data_bits)}. Требуется пароль для расшифровки."


class HilbertSteganographyApp:
    """Графический интерфейс для стеганографии на основе кривой Гильберта."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Стеганография - Кривая Гильберта")
        self.root.geometry("600x500")
        self.root.minsize(500, 400)
        
        # Настройка стиля
        style = ttk.Style()
        style.theme_use('clam')
        
        # Основной контейнер
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="Стеганография с кривой Гильберта", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Фрейм выбора операции
        operation_frame = ttk.LabelFrame(main_frame, text="Операция", padding="10")
        operation_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.operation_var = tk.StringVar(value="encode")
        encode_radio = ttk.Radiobutton(operation_frame, text="Закодировать текст в изображение", 
                                       variable=self.operation_var, value="encode",
                                       command=self.update_ui)
        encode_radio.pack(side=tk.LEFT, padx=(0, 20))
        
        decode_radio = ttk.Radiobutton(operation_frame, text="Извлечь текст из изображения", 
                                       variable=self.operation_var, value="decode",
                                       command=self.update_ui)
        decode_radio.pack(side=tk.LEFT)
        
        # Фрейм выбора файла
        file_frame = ttk.LabelFrame(main_frame, text="Файл изображения", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_button = ttk.Button(file_frame, text="Обзор...", command=self.browse_file)
        browse_button.pack(side=tk.RIGHT)
        
        # Фрейм ввода текста (только для кодирования)
        self.text_frame = ttk.LabelFrame(main_frame, text="Текст для записи", padding="10")
        self.text_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.text_entry = ttk.Entry(self.text_frame)
        self.text_entry.pack(fill=tk.X)
        
        # Фрейм ввода пароля
        self.password_frame = ttk.LabelFrame(main_frame, text="Пароль шифрования", padding="10")
        self.password_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(self.password_frame, textvariable=self.password_var, show="*")
        password_entry.pack(fill=tk.X)
        password_hint = ttk.Label(self.password_frame, text="Пароль используется для AES-GCM шифрования", 
                                  font=('Arial', 8), foreground='gray')
        password_hint.pack(fill=tk.X, pady=(5, 0))
        
        # Фрейм результата
        result_frame = ttk.LabelFrame(main_frame, text="Результат", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        self.result_text = scrolledtext.ScrolledText(result_frame, height=10, wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True)
        
        # Кнопки действий
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.action_button = ttk.Button(button_frame, text="Закодировать", command=self.perform_action)
        self.action_button.pack(side=tk.LEFT, padx=(0, 10))
        
        clear_button = ttk.Button(button_frame, text="Очистить", command=self.clear_result)
        clear_button.pack(side=tk.LEFT)
        
        # Статус бар
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Обновление UI
        self.update_ui()
    
    def update_ui(self):
        """Обновляет интерфейс в зависимости от выбранной операции."""
        operation = self.operation_var.get()
        
        if operation == "encode":
            self.text_frame.pack(fill=tk.X, pady=(0, 10))
            self.password_frame.pack(fill=tk.X, pady=(0, 10))
            self.action_button.config(text="Закодировать")
        else:
            self.text_frame.pack_forget()
            self.password_frame.pack(fill=tk.X, pady=(0, 10))
            self.action_button.config(text="Извлечь")
        
        self.clear_result()
    
    def browse_file(self):
        """Открывает диалог выбора файла."""
        filetypes = [
            ("Изображения", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif"),
            ("Все файлы", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=filetypes
        )
        
        if filename:
            self.file_path_var.set(filename)
            self.status_var.set(f"Файл выбран: {os.path.basename(filename)}")
    
    def perform_action(self):
        """Выполняет выбранную операцию в отдельном потоке."""
        file_path = self.file_path_var.get().strip()
        
        if not file_path:
            messagebox.showwarning("Предупреждение", "Пожалуйста, выберите файл изображения.")
            return
        
        operation = self.operation_var.get()
        
        # Блокируем кнопку на время выполнения
        self.action_button.config(state=tk.DISABLED)
        self.status_var.set("Обработка...")
        
        # Запускаем операцию в отдельном потоке
        thread = threading.Thread(target=self._run_operation, args=(operation, file_path))
        thread.daemon = True
        thread.start()
    
    def _run_operation(self, operation, file_path):
        """Запускает операцию обработки изображения."""
        try:
            password = self.password_var.get().strip()
            
            if operation == "encode":
                text = self.text_entry.get().strip()
                if not text:
                    self.root.after(0, lambda: messagebox.showwarning("Предупреждение", "Введите текст для записи."))
                    self.root.after(0, lambda: self.action_button.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_var.set("Готов к работе"))
                    return
                
                if not password:
                    self.root.after(0, lambda: messagebox.showwarning("Предупреждение", 
                        "Введите пароль для шифрования. Без пароля данные не будут защищены."))
                    self.root.after(0, lambda: self.action_button.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_var.set("Готов к работе"))
                    return
                
                success, result = ism_image(file_path, text, password)
            else:
                if not password:
                    self.root.after(0, lambda: messagebox.showwarning("Предупреждение", 
                        "Введите пароль для расшифровки."))
                    self.root.after(0, lambda: self.action_button.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_var.set("Готов к работе"))
                    return
                
                success, result = image_looking(file_path, password)
            
            # Обновляем UI в главном потоке
            self.root.after(0, lambda: self._update_result(success, result))
        except Exception as e:
            self.root.after(0, lambda: self._update_result(False, f"Произошла ошибка: {e}"))
    
    def _update_result(self, success, result):
        """Обновляет поле результата."""
        self.result_text.delete(1.0, tk.END)
        
        if success:
            self.result_text.insert(tk.END, result)
            self.result_text.config(fg="green")
            self.status_var.set("Операция выполнена успешно")
            if success and self.operation_var.get() == "decode":
                messagebox.showinfo("Результат", f"Извлеченный текст:\n{result}")
        else:
            self.result_text.insert(tk.END, f"Ошибка: {result}")
            self.result_text.config(fg="red")
            self.status_var.set("Ошибка выполнения")
            messagebox.showerror("Ошибка", result)
        
        self.action_button.config(state=tk.NORMAL)
    
    def clear_result(self):
        """Очищает поле результата."""
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(fg="black")
        self.status_var.set("Готов к работе")


def main():
    """Точка входа в приложение."""
    root = tk.Tk()
    app = HilbertSteganographyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
