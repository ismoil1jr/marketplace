"""Tovar rasmlarini mijoz sahifasi uchun tayyorlash.

Sotuvchi telefondan 3–8 MB JPG yuklaydi. Instagram ichidagi brauzerda, mobil
internetda bunday rasm sekin ochiladi. Shuning uchun har rasmdan ikki nusxa:
  medium    — 1200px WebP, mahsulot sahifasi uchun (~80–150 KB)
  thumbnail — 480px WebP, katalog kartochkasi uchun (~20–40 KB)
"""

import io
import os

import frappe
from frappe.utils.file_manager import save_file
from PIL import Image, ImageOps

SIZES = {"medium": 1200, "thumbnail": 480}
VECTOR_EXTS = (".svg",)


def process_gallery(doc, method=None):
	"""Item validate hook: yangi yoki almashtirilgan rasmlarni qayta ishlaydi."""
	for row in doc.get("gallery") or []:
		if not row.image or row.processed_image == row.image:
			continue
		if row.image.lower().endswith(VECTOR_EXTS):
			# SVG o'lchamsiz siqiladi, o'zini ishlatamiz
			row.medium = row.thumbnail = row.image
		else:
			for field, size in SIZES.items():
				row.set(field, make_webp(row.image, size, doc))
		row.processed_image = row.image

	# Desk ro'yxatlarida ham rasm ko'rinsin: birinchi galereya rasmi = Item.image
	if doc.get("gallery"):
		doc.image = doc.gallery[0].medium or doc.gallery[0].image


def make_webp(file_url, max_side, doc):
	file = frappe.get_doc("File", {"file_url": file_url})
	img = Image.open(io.BytesIO(file.get_content()))
	img = ImageOps.exif_transpose(img)  # telefon rasmlari ko'pincha yonboshlab saqlanadi
	if img.mode not in ("RGB", "RGBA"):
		img = img.convert("RGB")
	img.thumbnail((max_side, max_side), Image.LANCZOS)

	buf = io.BytesIO()
	img.save(buf, "WEBP", quality=80, method=6)
	base = os.path.splitext(os.path.basename(file_url))[0]
	saved = save_file(f"{base}-{max_side}.webp", buf.getvalue(), doc.doctype, doc.name, is_private=0)
	return saved.file_url
