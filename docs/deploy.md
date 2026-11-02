# Serverga o'rnatish (ERPNext v16 + marketplace)

Bu qo'llanmada 2026-11-02 da `161.97.176.253` serveriga qanday o'rnatganimiz yozilgan. Yangi serverda ham shu tartibda ishlang. Har bir qadamda **nima uchun** qilinishi ham yozilgan.

Server: Ubuntu 24.04, 4 CPU, 8 GB RAM, 100 GB SSD. Sayt nomi: `magazinlar.uz`.

> Qoida: `bench` hech qachon root ostida ishlamaydi. Root tizimni sozlaydi, `frappe` foydalanuvchisi esa bench'ni ishlatadi.

---

## 1. Tizimni tayyorlash (root)

```bash
ssh root@SERVER_IP
timedatectl set-timezone Asia/Tashkent
apt-get update && apt-get -y upgrade
reboot
```

**Swap.** Swap bo'lmasa, `bench build` paytida xotira yetmay qolishi mumkin:

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo "/swapfile none swap sw 0 0" >> /etc/fstab
echo "vm.swappiness=10" > /etc/sysctl.d/99-swap.conf && sysctl -p /etc/sysctl.d/99-swap.conf
```

**Firewall.** Faqat SSH, HTTP va HTTPS ochiq qoladi. `OpenSSH`ni birinchi qo'shing, aks holda serverdan chiqib qolasiz:

```bash
apt-get install -y ufw
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

**fail2ban.** SSH'ga parol terib kirishga urinayotgan IP'larni bloklaydi:

```bash
apt-get install -y fail2ban && systemctl enable --now fail2ban
```

## 2. `frappe` foydalanuvchisi (root)

```bash
adduser --disabled-password --gecos "" frappe
install -d -m 700 -o frappe -g frappe /home/frappe/.ssh
install -m 600 -o frappe -g frappe /root/.ssh/authorized_keys /home/frappe/.ssh/authorized_keys
chmod 755 /home/frappe          # nginx statik fayllarni o'qiy olishi uchun
```

`frappe` foydalanuvchisiga sudo **berilmaydi**. Kerakli ikki ruxsat (supervisor va nginx) quyida alohida beriladi.

## 3. Dasturlar (root)

Frappe v16 talablari:
- Python 3.14;
- Node 24 yoki undan yangi;
- MariaDB 10.6 dan 11.8 gacha. Ubuntu 24.04'ning o'zidagi 10.11 yetadi.

```bash
apt-get install -y software-properties-common ca-certificates curl gnupg git
add-apt-repository -y ppa:deadsnakes/ppa                 # Python 3.14

# Node 24: kalit bilan imzolangan repo ("curl | bash" emas)
install -d -m 755 /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" \
  > /etc/apt/sources.list.d/nodesource.list

apt-get update
apt-get install -y python3.14 python3.14-dev python3.14-venv python3-pip pipx build-essential pkg-config \
  mariadb-server mariadb-client libmariadb-dev redis-server nginx supervisor nodejs cron \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core libfontconfig1
npm install -g yarn
systemctl disable --now redis-server   # bench o'z Redis'larini ishga tushiradi
```

`libpango` paketlari WeasyPrint uchun kerak, u PDF cheklarni chiqaradi (`receipts.py`).

## 4. MariaDB (root)

`/etc/mysql/mariadb.conf.d/99-frappe.cnf` fayli. O'zbek va kirill harflari to'g'ri saqlanishi uchun `utf8mb4` kerak:

```ini
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
innodb_buffer_pool_size = 1G

[mysql]
default-character-set = utf8mb4
```

```bash
systemctl restart mariadb
```

Root paroli tasodifiy yaratiladi va faqat `frappe` o'qiy oladigan faylga yoziladi. Parolni hech qachon buyruq argumenti qilib bermang: u `ps` va `pgrep` chiqishida ko'rinib qoladi.

```bash
PW=$(openssl rand -base64 24 | tr -d "/+=" | cut -c1-24)
mariadb <<EOF
ALTER USER root@localhost IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD("$PW");
DELETE FROM mysql.global_priv WHERE User="";
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
EOF
install -m 600 -o frappe -g frappe /dev/null /home/frappe/.db_root_password
printf "%s" "$PW" > /home/frappe/.db_root_password
```

## 5. Supervisor ruxsati (root)

Bench jarayonlarni `supervisorctl` bilan qayta ishga tushiradi. `frappe`ga sudo bermaslik uchun supervisor soketi unga beriladi. `/etc/supervisor/supervisord.conf` faylidagi `[unix_http_server]` bo'limi:

```ini
chmod=0760
chown=frappe:frappe
```

```bash
systemctl restart supervisor
su - frappe -c "supervisorctl status"   # xatosiz chiqishi kerak
```

## 6. Bench va ilovalar (frappe)

```bash
ssh frappe@SERVER_IP
pipx install frappe-bench
pipx install uv                 # yangi bench venv'ni uv bilan yaratadi, usiz yiqiladi
export PATH=$HOME/.local/bin:$PATH

bench init frappe-bench --frappe-branch version-16 --python /usr/bin/python3.14
cd frappe-bench
bench get-app erpnext --branch version-16
```

**Marketplace'ni GitHub'dan olish.** Repo private, shuning uchun server unga faqat o'qiy oladigan deploy key bilan kiradi:

```bash
ssh-keygen -t ed25519 -N "" -C "server-deploy" -f ~/.ssh/github_marketplace
cat > ~/.ssh/config <<EOF
Host github.com
  IdentityFile ~/.ssh/github_marketplace
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
cat ~/.ssh/github_marketplace.pub
```

Chiqqan kalitni GitHub → repo → **Settings → Deploy keys → Add key** ga qo'shing. **«Allow write access» belgilanmasin.** Keyin:

```bash
ssh -T git@github.com            # "Hi ismoil1jr/marketplace!" chiqishi kerak
bench get-app git@github.com:ismoil1jr/marketplace.git --branch main
```

Bench GitHub manzilini `upstream` nomi bilan ulaydi, `origin` emas.

## 7. Supervisor va nginx konfiguratsiyasi

`bench setup production` Ubuntu 24.04'da yiqiladi: u ansible'ni `pip` bilan o'rnatmoqchi bo'ladi. Shuning uchun uning qadamlarini qo'lda bajaramiz.

**frappe:**

```bash
bench config restart_supervisor_on_update on
bench config dns_multitenant on        # bir nechta domen va SSL (lets-encrypt) uchun kerak
bench setup supervisor --yes
bench setup nginx --yes
```

**root:**

```bash
ln -sfn /home/frappe/frappe-bench/config/supervisor.conf /etc/supervisor/conf.d/frappe-bench.conf
ln -sfn /home/frappe/frappe-bench/config/nginx.conf /etc/nginx/conf.d/frappe-bench.conf
rm -f /etc/nginx/sites-enabled/default
```

Bench'ning nginx shabloni `log_format main` dan foydalanadi, Ubuntu'da esa u yo'q. Uni `/etc/nginx/conf.d/00-log-format.conf` fayliga yozing:

```nginx
log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                '$status $body_bytes_sent "$http_referer" '
                '"$http_user_agent" "$http_x_forwarded_for"';
```

```bash
supervisorctl reread && supervisorctl update
nginx -t && systemctl reload nginx
```

## 8. Sayt yaratish (frappe)

Sayt faqat Redis ishlab turganda yaratiladi. Redis'ni 7-qadamdagi supervisor ishga tushiradi, shuning uchun bu qadam 7-qadamdan keyin keladi.

Parollar argument qilib emas, vaqtincha konfiguratsiya orqali beriladi:

```bash
# root_password va admin_password vaqtincha common_site_config.json ga yoziladi
python3 - <<'PY'
import json
p = "sites/common_site_config.json"; c = json.load(open(p))
c["root_password"] = open("/home/frappe/.db_root_password").read().strip()
c["admin_password"] = "VAQTINCHALIK-PAROL"
json.dump(c, open(p, "w"), indent=1)
PY

nohup bench new-site magazinlar.uz --db-root-username root \
  --install-app erpnext --install-app marketplace > ~/new-site.log 2>&1 &
```

`nohup` SSH uzilib qolsa ham o'rnatishni to'xtatmaydi.

O'rnatish tugagach (`~/new-site.log`ni kuzating), ikkala parolni konfiguratsiyadan **o'chiring**. Keyin:

```bash
bench use magazinlar.uz
bench --site magazinlar.uz set-config host_name "http://SERVER_IP"   # domen olingach https://magazinlar.uz
bench --site magazinlar.uz enable-scheduler
bench setup add-domain www.magazinlar.uz --site magazinlar.uz
bench setup add-domain SERVER_IP --site magazinlar.uz               # domen olinmaguncha IP orqali ochilsin
bench setup nginx --yes
bench --site magazinlar.uz set-admin-password                        # parolni o'zi so'raydi
```

So'ng root ostida `nginx -t && systemctl reload nginx`.

Brauzerda `http://SERVER_IP` ni oching va Administrator bilan kirib, sozlash ustasini (setup wizard) to'ldiring:
- Mamlakat: Uzbekistan;
- Valyuta: UZS;
- Vaqt zonasi: Asia/Tashkent;
- Kompaniya nomi.

Ustadan keyin bir marta migrate qiling. U so'm belgisini va yangi kompaniya sozlamalarini to'g'rilaydi:

```bash
bench --site magazinlar.uz migrate
```

## 9. Yangi kodni chiqarish (har safar)

Lokal kompyuterda `apps/marketplace`dan commit va push qiling. Keyin serverda:

```bash
ssh frappe@SERVER_IP
cd ~/frappe-bench
git -C apps/marketplace pull upstream main
bench --site magazinlar.uz migrate        # doctype yoki patch o'zgargan bo'lsa
bench build --app marketplace             # JS yoki CSS o'zgargan bo'lsa
bench restart
```

## 10. Domen va SSL (domen olingach)

1. Registrator panelida `magazinlar.uz` va `www` uchun A-yozuvni server IP manziliga yo'naltiring.
2. root ostida certbot o'rnating va sertifikat oling. Keyin sayt konfiguratsiyasiga sertifikat yo'lini yozib, `bench setup nginx` qiling.
3. `host_name` qiymatini `https://magazinlar.uz` ga o'zgartiring, keyin Payme, Click, SMM havolalari va Telegram webhook'ni yangilang.

## Duch kelgan xatolar

| Belgi | Sababi | Yechim |
|---|---|---|
| `No such file or directory: 'uv'` | Yangi bench `uv` bilan ishlaydi | `pipx install uv` |
| `sudo supervisorctl status ... exit status 1` | `frappe`da sudo yo'q | 5-qadam: supervisor soketi `frappe`ga beriladi |
| `Redis Queue ... Connection refused` | Sayt Redis ishlamay turib yaratilgan | Avval 7-qadam, keyin sayt |
| `unknown log format "main"` | Ubuntu nginx'ida format yo'q | `00-log-format.conf` |
| Nginx'da qo'shimcha domen yo'q | `dns_multitenant` o'chiq | `bench config dns_multitenant on` |
| `git pull origin` ishlamaydi | Bench remote'ni `upstream` deb ataydi | `git pull upstream main` |
| `pkill -f ...` natija bermaydi | Pattern SSH buyrug'ining o'zini ham topib, uni o'ldiradi | `pgrep -f "[b]ench ..."` ko'rinishidagi pattern |
