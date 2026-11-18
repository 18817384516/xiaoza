"""Validate and normalize user supplied reference images before any paid call."""
import base64
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from .modeling import ModelingError


def normalize_reference(value):
    if not isinstance(value, str) or len(value) > 4_000_000 or not value.startswith('data:image/'):
        raise ModelingError('参考图需要是本机上传的 PNG、JPG 或 WebP 图片（不超过3 MB）。', code='reference_invalid')
    try:
        header, encoded = value.split(',', 1)
        if header not in ('data:image/png;base64', 'data:image/jpeg;base64', 'data:image/webp;base64'):
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(raw)) as source:
            if min(source.size) < 32 or source.width * source.height > 16_000_000:
                raise ValueError()
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1536, 1536))
            output = BytesIO()
            image.save(output, 'JPEG', quality=92)
        return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ModelingError('参考图无法读取，请选择至少32×32像素的 PNG、JPG 或 WebP 图片。', code='reference_invalid') from None
