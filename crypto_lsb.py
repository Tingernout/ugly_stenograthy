"""
Модули для криптографии и LSB-внедрения в стеганографии.

Часть 1: Криптография (использует библиотеку cryptography)
Часть 2: Помощники для LSB-внедрения
"""

import os
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# =============================================================================
# Часть 1: Криптография
# =============================================================================

def _generate_salt() -> bytes:
    """Генерирует случайную соль (16 байт)."""
    return os.urandom(16)


def _derive_key(password: str, salt: bytes) -> bytes:
    """
    Деривирует ключ из пароля и соли используя PBKDF2HMAC.
    
    Args:
        password: Строка пароля
        salt: Соль (байты)
    
    Returns:
        Ключ длиной 32 байта (256 бит) для AES-256
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend()
    )
    return kdf.derive(password.encode('utf-8'))


def _bytes_to_bits(data: bytes) -> str:
    """Преобразует байты в бинарную строку ('011010...')."""
    return ''.join(format(byte, '08b') for byte in data)


def _bits_to_bytes(bits: str) -> bytes:
    """Преобразует бинарную строку обратно в байты."""
    # Дополняем до кратности 8, если нужно
    if len(bits) % 8 != 0:
        raise ValueError(f"Длина бинарной строки должна быть кратна 8, получено: {len(bits)}")
    
    bytes_list = []
    for i in range(0, len(bits), 8):
        byte = bits[i:i+8]
        bytes_list.append(int(byte, 2))
    
    return bytes(bytes_list)


def encrypt_message(password: str, message: str) -> str:
    """
    Шифрует сообщение с использованием AES-GCM.
    
    Args:
        password: Пароль для шифрования
        message: Исходное сообщение (текст)
    
    Returns:
        Бинарная строка формата:
        [32 бита: размер данных] + [соль] + [nonce] + [auth_tag] + [шифротекст]
        
        Все компоненты кодируются в бинарный формат ('011010...')
    """
    # Генерируем случайную соль
    salt = _generate_salt()
    
    # Деривируем ключ из пароля
    key = _derive_key(password, salt)
    
    # Создаем AESGCM объект
    aesgcm = AESGCM(key)
    
    # Генерируем случайный nonce (12 байт - рекомендуемый размер для GCM)
    nonce = os.urandom(12)
    
    # Шифруем сообщение
    ciphertext = aesgcm.encrypt(nonce, message.encode('utf-8'), None)
    
    # ciphertext содержит: зашифрованные данные + auth_tag (последние 16 байт)
    # Auth_tag автоматически добавляется библиотекой в конец ciphertext
    
    # Формируем полезную нагрузку:
    # [размер сообщения в байтах (4 байта)] + [соль (16 байт)] + [nonce (12 байт)] + [ciphertext]
    message_length = len(message.encode('utf-8'))
    length_bytes = message_length.to_bytes(4, byteorder='big')
    
    payload = length_bytes + salt + nonce + ciphertext
    
    # Преобразуем всё в бинарную строку
    binary_payload = _bytes_to_bits(payload)
    
    return binary_payload


def decrypt_message(password: str, binary_payload: str) -> str:
    """
    Расшифровывает сообщение из бинарной строки.
    
    Args:
        password: Пароль для расшифровки
        binary_payload: Бинарная строка, полученная от encrypt_message
    
    Returns:
        Расшифрованное сообщение (текст)
    
    Raises:
        ValueError: Если пароль неверный или данные повреждены
    """
    # Преобразуем бинарную строку обратно в байты
    payload = _bits_to_bytes(binary_payload)
    
    # Парсим payload:
    # [4 байта: размер] + [16 байт: соль] + [12 байт: nonce] + [остальное: ciphertext]
    
    if len(payload) < 4 + 16 + 12 + 16:  # минимальный размер (данные + тег)
        raise ValueError("Повреждённые данные: слишком короткая полезная нагрузка")
    
    # Извлекаем размер сообщения
    message_length = int.from_bytes(payload[0:4], byteorder='big')
    
    # Извлекаем соль
    salt = payload[4:20]
    
    # Извлекаем nonce
    nonce = payload[20:32]
    
    # Извлекаем ciphertext (включая auth_tag)
    ciphertext = payload[32:]
    
    # Деривируем ключ из пароля
    key = _derive_key(password, salt)
    
    # Создаем AESGCM объект
    aesgcm = AESGCM(key)
    
    # Расшифровываем (если пароль неверный или данные повреждены, будет исключение)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    
    return plaintext.decode('utf-8')


# =============================================================================
# Часть 2: Помощники для LSB-внедрения
# =============================================================================

def embed_bit(color_value: int, bit: str) -> int:
    """
    Заменяет младший бит (LSB) значения цвета на переданный бит.
    
    Args:
        color_value: Значение цвета канала (0-255)
        bit: Бит для внедрения ('0' или '1')
    
    Returns:
        Новое значение цвета с изменённым LSB
    
    Raises:
        ValueError: Если цвет_value не в диапазоне 0-255 или bit не '0'/'1'
    """
    if not 0 <= color_value <= 255:
        raise ValueError(f"color_value должен быть в диапазоне 0-255, получено: {color_value}")
    
    if bit not in ('0', '1'):
        raise ValueError(f"bit должен быть '0' или '1', получено: {bit}")
    
    # Очищаем младший бит и устанавливаем новый
    bit_int = int(bit)
    return (color_value & 0xFE) | bit_int


def extract_bit(color_value: int) -> str:
    """
    Извлекает младший бит (LSB) из значения цвета.
    
    Args:
        color_value: Значение цвета канала (0-255)
    
    Returns:
        Строка '0' или '1'
    
    Raises:
        ValueError: Если color_value не в диапазоне 0-255
    """
    if not 0 <= color_value <= 255:
        raise ValueError(f"color_value должен быть в диапазоне 0-255, получено: {color_value}")
    
    return str(color_value & 1)


# =============================================================================
# Примеры использования (для тестирования)
# =============================================================================

if __name__ == "__main__":
    # Тест криптографии
    print("=== Тест криптографии ===")
    password = "my_secret_password"
    original_message = "Привет, мир! Это секретное сообщение."
    
    print(f"Исходное сообщение: {original_message}")
    
    # Шифрование
    encrypted = encrypt_message(password, original_message)
    print(f"Зашифровано (первые 100 символов): {encrypted[:100]}...")
    print(f"Длина бинарной строки: {len(encrypted)} бит")
    
    # Расшифровка
    decrypted = decrypt_message(password, encrypted)
    print(f"Расшифровано: {decrypted}")
    
    assert original_message == decrypted, "Ошибка: сообщения не совпадают!"
    print("✓ Тест криптографии пройден\n")
    
    # Тест LSB функций
    print("=== Тест LSB функций ===")
    
    test_values = [0, 1, 127, 128, 255]
    for val in test_values:
        # Внедряем '0'
        embedded_0 = embed_bit(val, '0')
        extracted_0 = extract_bit(embedded_0)
        print(f"Значение {val}: LSB='0' -> {embedded_0}, извлечено: '{extracted_0}'")
        assert extracted_0 == '0', f"Ошибка извлечения '0' для {val}"
        
        # Внедряем '1'
        embedded_1 = embed_bit(val, '1')
        extracted_1 = extract_bit(embedded_1)
        print(f"Значение {val}: LSB='1' -> {embedded_1}, извлечено: '{extracted_1}'")
        assert extracted_1 == '1', f"Ошибка извлечения '1' для {val}"
    
    print("✓ Тест LSB функций пройден\n")
    
    # Интеграционный тест: шифрование + LSB внедрение
    print("=== Интеграционный тест ===")
    message = "Secret"
    password = "test123"
    
    # Шифруем
    binary_data = encrypt_message(password, message)
    print(f"Зашифрованные данные: {len(binary_data)} бит")
    
    # Представим, что у нас есть массив пикселей (нужно минимум len(binary_data) пикселей)
    pixels = [128] * len(binary_data)
    
    # Внедряем биты в пиксели
    for i, bit in enumerate(binary_data):
        pixels[i] = embed_bit(pixels[i], bit)
    
    # Извлекаем биты обратно
    extracted_bits = ""
    for i in range(len(binary_data)):
        extracted_bits += extract_bit(pixels[i])
    
    # Расшифровываем
    try:
        decrypted_message = decrypt_message(password, extracted_bits)
        print(f"Извлечённое сообщение: {decrypted_message}")
        assert message == decrypted_message, "Сообщения не совпадают!"
        print("✓ Интеграционный тест пройден")
    except Exception as e:
        print(f"✗ Ошибка при расшифровке: {e}")
