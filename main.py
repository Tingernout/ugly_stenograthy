import cv2
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
from crypto_lsb import encrypt_message, decrypt_message, embed_bit, extract_bit


def d2xy(n, d):
    # Перевод номера точки d в координаты x,y кривой Гильберта порядка n
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

    max_order = 0
    for order in range(3, 8):
        min_dim = 2 ** order
        if height >= min_dim and width >= min_dim * 4:
            max_order = order
        else:
            break

    if max_order < 3:
        return False, "Изображение слишком маленькое для кривой Гильберта (минимум 8x32 пикселей)."

    points = hilbert_curve_points(max_order)
    modify_image = isnachal_photo.copy()

    if password:
        binary_payload = encrypt_message(password, text)
    else:
        binary_payload = ''.join(format(ord(c), '08b') for c in text)

    length_prefix = format(len(binary_payload), '032b')
    full_payload = length_prefix + binary_payload

    max_capacity = len(points) * 3
    if len(full_payload) > max_capacity:
        return False, f"Текст слишком большой для этого изображения. Максимум бит: {max_capacity}, требуется: {len(full_payload)}."

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

    # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Диалог выбора пути сохранения ---
    # Создаем скрытое окно для диалога (так как функция может вызываться из потока)
    # Примечание: В идеале диалог должен вызываться из главного потока GUI,
    # но для простоты мы создадим временное root окно здесь, если оно не передано.
    # Однако, лучше передать root из класса, но чтобы не ломать структуру,
    # сделаем хитрость: вернем изображение в класс, а сохранение сделаем там.
    # НО так как функция возвращает строку статуса, изменим логику:
    # Функция теперь возвращает обработанное изображение и статус, а сохраняет его вызывающая сторона.
    # Или проще: передадим root в функцию. Но у нас функция чистая.

    # Давайте изменим подход: функция вернет успех и само изображение (numpy array),
    # а сохранение выполнит GUI поток. Это правильнее для Tkinter.
    return True, modify_image, f"Изображение обработано (порядок {max_order}). Выберите место для сохранения."


# Обертка для сохранения, чтобы не менять сигнатуру возврата кардинально в других местах,
# но в данном случае лучше изменить логику внутри класса HilbertSteganographyApp.
# Я изменю функцию ism_image, чтобы она возвращала массив изображения вместо пути,
# и добавлю новую функцию для сохранения.

def save_encrypted_image(image_array, initial_dir=None):
    """Открывает диалог сохранения и сохраняет изображение."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    file_path = filedialog.asksaveasfilename(
        title="Сохранить зашифрованное изображение как...",
        defaultextension=".png",
        filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        initialfile="encrypted_image.png",
        initialdir=initial_dir
    )
    root.destroy()

    if not file_path:
        return False, "Сохранение отменено пользователем."

    try:
        cv2.imwrite(file_path, image_array)
        return True, f"Файл успешно сохранен:\n{file_path}"
    except Exception as e:
        return False, f"Ошибка при сохранении файла: {e}"


def image_looking(input_image, password=None):
    """Извлекает и расшифровывает текст из изображения по кривой Гильберта."""
    if not os.path.exists(input_image):
        return False, "Файл не найден."

    modify_image = cv2.imread(input_image)
    if modify_image is None:
        return False, "Ошибка: невозможно загрузить изображение."

    height, width, _ = modify_image.shape

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

    extracted_bits = ""
    max_bits = len(points) * 3

    for (x, y) in points:
        px_x = x * 4
        if y >= height or px_x >= width:
            break
        try:
            pixel = modify_image[y, px_x]
            for channel in range(3):
                extracted_bits += extract_bit(pixel[channel])
                if len(extracted_bits) >= max_bits:
                    break
        except (IndexError, ValueError):
            continue

    if len(extracted_bits) < 32:
        return False, "Недостаточно данных для чтения длины."

    data_length = int(extracted_bits[:32], 2)
    data_bits = extracted_bits[32:32 + data_length]

    if len(data_bits) < data_length:
        return False, f"Недостаточно данных. Ожидалось: {data_length}, получено: {len(data_bits)}"

    if password:
        try:
            decrypted_text = decrypt_message(password, data_bits)
            return True, decrypted_text
        except Exception as e:
            return False, f"Ошибка расшифровки: неверный пароль или повреждённые данные. ({e})"
    else:
        return True, f"Извлечено бит: {len(data_bits)}. Требуется пароль для расшифровки."


class HilbertSteganographyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Стеганография - Кривая Гильберта")
        self.root.geometry("600x500")
        self.root.minsize(500, 400)

        style = ttk.Style()
        style.theme_use('clam')

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="Стеганография с кривой Гильберта",
                                font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))

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

        file_frame = ttk.LabelFrame(main_frame, text="Файл изображения", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))

        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var)
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_button = ttk.Button(file_frame, text="Обзор...", command=self.browse_file)
        browse_button.pack(side=tk.RIGHT)

        self.text_frame = ttk.LabelFrame(main_frame, text="Текст для записи", padding="10")
        self.text_frame.pack(fill=tk.X, pady=(0, 10))

        self.text_entry = ttk.Entry(self.text_frame)
        self.text_entry.pack(fill=tk.X)

        self.password_frame = ttk.LabelFrame(main_frame, text="Пароль шифрования", padding="10")
        self.password_frame.pack(fill=tk.X, pady=(0, 10))

        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(self.password_frame, textvariable=self.password_var, show="*")
        password_entry.pack(fill=tk.X)
        password_hint = ttk.Label(self.password_frame, text="Пароль используется для AES-GCM шифрования",
                                  font=('Arial', 8), foreground='gray')
        password_hint.pack(fill=tk.X, pady=(5, 0))

        result_frame = ttk.LabelFrame(main_frame, text="Результат", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True)

        self.result_text = scrolledtext.ScrolledText(result_frame, height=10, wrap=tk.WORD)
        self.result_text.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        self.action_button = ttk.Button(button_frame, text="Закодировать", command=self.perform_action)
        self.action_button.pack(side=tk.LEFT, padx=(0, 10))

        clear_button = ttk.Button(button_frame, text="Очистить", command=self.clear_result)
        clear_button.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        self.update_ui()

    def update_ui(self):
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
        file_path = self.file_path_var.get().strip()

        if not file_path:
            messagebox.showwarning("Предупреждение", "Пожалуйста, выберите файл изображения.")
            return

        operation = self.operation_var.get()

        self.action_button.config(state=tk.DISABLED)
        self.status_var.set("Обработка...")

        thread = threading.Thread(target=self._run_operation, args=(operation, file_path))
        thread.daemon = True
        thread.start()

    def _run_operation(self, operation, file_path):
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
                                                                      "Введите пароль для шифрования."))
                    self.root.after(0, lambda: self.action_button.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_var.set("Готов к работе"))
                    return

                # Вызываем обновленную функцию, которая возвращает изображение
                success, result_data, message = ism_image(file_path, text, password)

                if success:
                    # Если успешно, открываем диалог сохранения в главном потоке
                    # Передаем изображение и начальную директорию
                    initial_dir = os.path.dirname(file_path)
                    self.root.after(0, lambda: self._save_file_dialog(result_data, initial_dir, message))
                else:
                    self.root.after(0, lambda: self._update_result(False, result_data))  # result_data тут ошибка

            else:
                if not password:
                    self.root.after(0, lambda: messagebox.showwarning("Предупреждение",
                                                                      "Введите пароль для расшифровки."))
                    self.root.after(0, lambda: self.action_button.config(state=tk.NORMAL))
                    self.root.after(0, lambda: self.status_var.set("Готов к работе"))
                    return

                success, result = image_looking(file_path, password)
                self.root.after(0, lambda: self._update_result(success, result))

        except Exception as e:
            self.root.after(0, lambda: self._update_result(False, f"Произошла ошибка: {e}"))

    def _save_file_dialog(self, image_array, initial_dir, message):
        """Вызывает диалог сохранения после успешного шифрования."""
        # Показываем сообщение о подготовке
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, message)

        # Открываем диалог
        saved_successfully, save_result = save_encrypted_image(image_array, initial_dir)

        if saved_successfully:
            self._update_result(True, save_result)
        else:
            # Если пользователь нажал "Отмена" или ошибка сохранения
            if "отменено" in save_result.lower():
                self.status_var.set("Сохранение отменено")
                self.result_text.insert(tk.END, "\n\nОперация шифрования завершена, но файл не был сохранен.")
            else:
                self._update_result(False, save_result)

        self.action_button.config(state=tk.NORMAL)

    def _update_result(self, success, result):
        self.result_text.delete(1.0, tk.END)

        if success:
            self.result_text.insert(tk.END, result)
            self.result_text.config(fg="green")
            self.status_var.set("Операция выполнена успешно")
            if self.operation_var.get() == "decode":
                messagebox.showinfo("Результат", f"Извлеченный текст:\n{result}")
        else:
            self.result_text.insert(tk.END, f"Ошибка: {result}")
            self.result_text.config(fg="red")
            self.status_var.set("Ошибка выполнения")
            messagebox.showerror("Ошибка", result)

        self.action_button.config(state=tk.NORMAL)

    def clear_result(self):
        self.result_text.delete(1.0, tk.END)
        self.result_text.config(fg="black")
        self.status_var.set("Готов к работе")


def main():
    root = tk.Tk()
    app = HilbertSteganographyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()