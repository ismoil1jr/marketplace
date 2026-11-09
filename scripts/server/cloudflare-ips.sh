#!/bin/sh
# Cloudflare IP ro'yxatidan nginx real_ip konfiguratsiyasini yasaydi.
# Ishlatish (root):  sh scripts/server/cloudflare-ips.sh > /etc/nginx/conf.d/05-cloudflare-realip.conf && nginx -t && systemctl reload nginx
# Cloudflare ro'yxati kamdan-kam o'zgaradi; yiliga bir marta qayta ishlatish yetarli.
set -e
v4=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v4)
v6=$(curl -fsS --max-time 20 https://www.cloudflare.com/ips-v6)
[ -n "$v4" ] && [ -n "$v6" ] || { echo "Cloudflare ro'yxati olinmadi" >&2; exit 1; }
cat <<HEAD
# Cloudflare orqasida haqiqiy mijoz IP'si. Yasalgan: $(date +%F) (scripts/server/cloudflare-ips.sh)
# Faqat shu manzillardan kelgan ulanishlarda CF-Connecting-IP sarlavhasiga ishoniladi — boshqa IP shu sarlavhani
# yuborsa, e'tiborga olinmaydi (aldab bo'lmaydi). Cloudflare'ga o'tilmagan paytda fayl hech narsani o'zgartirmaydi.
# Natija: \$remote_addr = mijoz IP'si -> nginx limitlari (10-himoya.conf), access.log, fail2ban va Frappe
# (bench nginx'i X-Forwarded-For ga \$remote_addr yozadi, Frappe request_ip shundan) hammasi haqiqiy IP bilan ishlaydi.
HEAD
for ip in $v4 $v6; do echo "set_real_ip_from $ip;"; done
cat <<TAIL
real_ip_header CF-Connecting-IP;
TAIL
