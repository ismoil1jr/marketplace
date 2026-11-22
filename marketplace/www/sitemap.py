# Frappe'ning /sitemap.xml'i bizda bo'sh edi (do'kon va tovar sahifalari dinamik yo'l) — o'rniga shu.
# Ilovalar ichida marketplace oxirgi o'rnatilgan, shuning uchun bu fayl frappe/www/sitemap.py'dan ustun.
from marketplace import seo

no_cache = 1
base_template_path = "www/sitemap.xml"


def get_context(context):
	return {"links": seo.sitemap_links()}
