import cv2
import os


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


def image_looking(input_image):
    if not os.path.exists(input_image):
        print("Файл не найден.")
        return
    
    modify_image = cv2.imread(input_image)
    if modify_image is None:
        print("Ошибка: невозможно загрузить изображение. Проверьте путь и формат файла.")
        return

    image_text = ""
    height, width, _ = modify_image.shape

    order = 3  # 3-й порядок -> 8x8 квадрат
    points = hilbert_curve_points(order)

    # Проверим, что изображение достаточно большое по ширине и высоте
    if height < 8 or width < 8*4:
        print("Изображение слишком маленькое для кривой Гильберта 3-го порядка с шагом 4 по ширине.")
        return

    for (x, y) in points:
        px_x = x * 4
        if y >= height or px_x >= width:
            break
        px = modify_image[y, px_x][0]
        c = chr(px)
        if c == "@":  # стоп-символ
            break
        image_text += c
    print("Извлеченный текст:", image_text)


def ism_image(input_image, text):
    if not os.path.exists(input_image):
        print("Файл не найден.")
        return
    
    isnachal_photo = cv2.imread(input_image)
    if isnachal_photo is None:
        print("Ошибка: невозможно загрузить изображение. Проверьте путь и формат файла.")
        return

    height, width, _ = isnachal_photo.shape
    modify_image = isnachal_photo.copy()

    order = 3
    points = hilbert_curve_points(order)

    if height < 8 or width < 8*4:
        print("Изображение слишком маленькое для кривой Гильберта 3-го порядка с шагом 4 по ширине.")
        return

    ism_text = [ord(i) for i in text]
    print("Записываем текст в изображение...")

    for i, (x, y) in enumerate(points):
        if i >= len(ism_text):
            break
        px_x = x * 4
        if px_x >= width:
            print(f"Предупреждение: координата x={px_x} выходит за пределы ширины изображения ({width}). Запись остановлена.")
            break
        modify_image[y, px_x][0] = ism_text[i]

    output_path = "modify_image.png"
    cv2.imwrite(output_path, modify_image)
    print(f"Текст успешно записан в изображение и сохранен как {output_path}.")


def menu():
    print("\n1. Закодировать изображение")
    print("2. Посмотреть, что спрятано")


while True:
    try:
        menu()
        choice = input("Что вы хотите сделать: ")
        choice_int = int(choice)
        if choice_int == 1:
            input_image = input("\nВведите путь к фото\n")
            text = input("Введите текст\n") + "@"  # Добавляем стоп-символ
            ism_image(input_image, text)

        elif choice_int == 2:
            input_image = input("\nВведите путь к фото\n")
            image_looking(input_image)

        else:
            print("Неверный выбор, попробуйте снова.")
    except ValueError:
        print("Ошибка: введите число (1 или 2).")
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем.")
        break
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
