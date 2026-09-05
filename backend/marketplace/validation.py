import base64
import binascii
import io
import re
import warnings

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from PIL import Image, ImageOps, UnidentifiedImageError


def phone_number(value):
    value = re.sub(r"[\s()\-]", "", value)
    if not re.fullmatch(r"\+998\d{9}", value):
        raise serializers.ValidationError("Укажите номер Узбекистана: +998 и 9 цифр.")
    return value


def birth_date(value):
    today = timezone.localdate()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if not 16 <= age <= 65:
        raise serializers.ValidationError("Возраст должен быть от 16 до 65 лет включительно.")
    return value


def password_pair(attrs):
    password = attrs["password"]
    if password != attrs["password_confirm"]:
        raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
    if len(password) < 8 or not any(c.isupper() for c in password) or not re.search(r"\d", password) or not any(c in "!-_@#$&.<=>," for c in password):
        raise serializers.ValidationError({"password": "Минимум 8 символов, одна заглавная буква, цифра и символ !-_@#$&.<=>,"})
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages}) from exc
    return attrs


def skills_list(value):
    if not isinstance(value, list) or len(value) > 30 or any(not isinstance(s, str) or not s.strip() or len(s) > 60 for s in value):
        raise serializers.ValidationError("Укажите до 30 навыков, каждый длиной от 1 до 60 символов.")
    return list(dict.fromkeys(s.strip() for s in value))


def image_data(value):
    if not value:
        return ""
    if len(value) > 2_800_000:
        raise serializers.ValidationError("Изображение должно быть не больше 2 МБ.")
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\r\n]+)", value)
    if not match:
        raise serializers.ValidationError("Загрузите изображение PNG, JPEG или WebP.")
    try:
        data = base64.b64decode(match[2], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise serializers.ValidationError("Повреждённое изображение.") from exc
    valid = {"png": data.startswith(b"\x89PNG\r\n\x1a\n"), "jpeg": data.startswith(b"\xff\xd8\xff"), "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP"}
    if not valid[match[1]]:
        raise serializers.ValidationError("Содержимое не соответствует формату изображения.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as uploaded:
                if uploaded.width * uploaded.height > 16_000_000:
                    raise ValueError("Image too large")
                uploaded.load()
                normalized = ImageOps.exif_transpose(uploaded).convert("RGB")
                normalized.thumbnail((1600, 1600))
                output = io.BytesIO()
                normalized.save(output, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise serializers.ValidationError("Повреждённое или слишком большое изображение.") from exc
