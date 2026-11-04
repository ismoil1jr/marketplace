"""Payme va Click: mijozni to'lov sahifasiga yuborish va to'lov natijasini buyurtmaga yozish.

Pul platformaga emas, do'konning (MChJ) o'z kassasiga tushadi. Kassa kalitlari Shop formasida
(permlevel 2, faqat platforma admini ko'radi) Password maydonlarida shifrlangan holda turadi.

* Payme: checkout.paycom.uz/<base64("m=..;ac.order_id=..;a=tiyin;c=qaytish")>. Telefonda bu sahifa
  "Payme ilovasida to'lash" tugmasi bilan Payme ilovasini ochadi.
* Click: my.click.uz/services/pay?... Telefonda Click ilovasi o'rnatilgan bo'lsa, havola o'sha ilovada ochiladi.

To'lov tasdig'i provayderning serverdan-serverga so'rovi (webhook) bilan keladi: payme.py, click.py.
Ikkalasi ham oxirida shu yerdagi mark_paid / mark_refunded'ni chaqiradi.
"""

import base64
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint, flt, get_url

PAYME_URL = {False: "https://checkout.paycom.uz", True: "https://checkout.test.paycom.uz"}
CLICK_URL = "https://my.click.uz/services/pay"


def url_shop():
	"""Har bir do'konning o'z endpoint'i: .../payme.callback?dokon=<Shop> (Click Prepare/Complete'da ham).
	Havoladan (query) o'qiladi — so'rov tanasidagi qiymat uni almashtira olmaydi. Parametrsiz eski manzil — None."""
	request = getattr(frappe.local, "request", None)
	return ((request.args.get("dokon") if request else None) or "").strip() or None


def gateway_status(shop_name):
	"""{"Payme": "live"|None, "Click": "live"|None}. live — do'konda yoqilgan va kassa kalitlari kiritilgan."""
	shop = frappe.get_doc("Shop", shop_name)
	payme_key = shop.get_password(
		"payme_test_key" if cint(shop.payme_test_mode) else "payme_key", raise_exception=False
	)
	click_key = shop.get_password("click_secret_key", raise_exception=False)
	return {
		"Payme": "live" if shop.enable_payme and shop.payme_merchant_id and payme_key else None,
		"Click": "live" if shop.enable_click and shop.click_service_id and shop.click_merchant_id and click_key else None,
	}


def checkout_url(so, method):
	"""Mijoz yuboriladigan to'lov sahifasi."""
	if not gateway_status(so.shop).get(method):
		frappe.throw(_("Bu to‘lov usuli hozircha ishlamaydi"))

	# Mijoz qaysi manzildan kirgan bo'lsa (telefonda LAN IP yoki domen), to'lovdan keyin o'shanga qaytadi
	request = getattr(frappe.local, "request", None)
	origin = request.host_url.rstrip("/") if request else get_url()
	return_url = f"{origin}/s/{so.shop}/buyurtma/{so.name}"

	shop = frappe.get_doc("Shop", so.shop)
	amount = flt(so.grand_total)
	if method == "Payme":
		params = f"m={shop.payme_merchant_id};ac.order_id={so.name};a={to_tiyin(amount)};l=uz;c={return_url}"
		return f"{PAYME_URL[bool(cint(shop.payme_test_mode))]}/{base64.b64encode(params.encode()).decode()}"
	return CLICK_URL + "?" + urlencode(
		{
			"service_id": shop.click_service_id,
			"merchant_id": shop.click_merchant_id,
			"amount": f"{amount:.2f}",
			"transaction_param": so.name,
			"return_url": return_url,
		}
	)


def to_tiyin(amount):
	return int(round(flt(amount) * 100))


def mark_paid(order, method, provider_ref=None):
	"""Buyurtmani to'langan qiladi va sotuvchiga xabar beradi."""
	so = frappe.get_doc("Sales Order", order)
	if so.payment_status == "To'langan":
		return
	so.db_set({"payment_status": "To'langan", "payment_method": method})
	so.add_comment("Info", _("{0} orqali to‘landi {1}").format(method, provider_ref or ""))
	from marketplace.kassa import stamp_paid

	stamp_paid(so.name)

	from marketplace.orders import confirm_order
	from marketplace.seller_desk import notify_shop

	# To'lov o'tdi — buyurtma endi do'konga "Yangi buyurtma" bo'lib boradi (naqd tanlangan bo'lsa — "To'landi")
	if not confirm_order(so.name):
		notify_shop(so, _("To‘landi {0}: {1} — {2}").format(so.name, so.customer_name, _money(so)))


def mark_refunded(order, method, provider_ref=None):
	"""To'lovdan keyin bekor qilindi (pul mijozga qaytdi): buyurtma bekor, zaxira bo'shaydi."""
	so = frappe.get_doc("Sales Order", order)
	so.db_set("payment_status", "Bekor")
	so.add_comment("Info", _("{0} to‘lovi bekor qilindi, pul qaytarildi {1}").format(method, provider_ref or ""))
	if so.docstatus == 1 and not flt(so.per_delivered):
		so.flags.ignore_permissions = True
		so.cancel()

	from marketplace.seller_desk import notify_shop

	if so.get("mp_placed"):
		notify_shop(so, _("To‘lov bekor qilindi {0}: {1} — {2}").format(so.name, so.customer_name, _money(so)))


def _money(so):
	return frappe.utils.fmt_money(so.grand_total, currency=so.currency)


def before_request():
	"""Payme so'rovi `Authorization: Basic Paycom:<kalit>` bilan keladi. Frappe buni o'zining API kaliti
	deb tekshirib, so'rovni rad etadi. Shu manzil uchun sarlavhani olib qo'yamiz, tekshiruvni payme.py qiladi."""
	request = getattr(frappe.local, "request", None)
	if request and request.path.rstrip("/") == "/api/method/marketplace.payme.callback":
		frappe.local.payme_authorization = request.environ.pop("HTTP_AUTHORIZATION", "")
