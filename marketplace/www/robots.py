# /robots.txt: kabinet va API yopiq, sitemap manzili ko'rsatilgan (frappe/www/robots.py o'rniga).
from marketplace import seo

base_template_path = "www/robots.txt"


def get_context(context):
	return {"robots_txt": seo.robots_txt()}
