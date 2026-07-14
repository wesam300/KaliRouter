# نقل وتشغيل KaliGPT على Kali Linux

## 1. انسخ المشروع إلى Kali Linux

### الطريقة الأولى - Git Clone (مباشر على Kali):
```bash
git clone https://github.com/SudoHopeX/KaliGPT.git
cd KaliGPT
```

### الطريقة الثانية - USB / SCP (من Windows):
```bash
# على Windows - استخدم scp (PowerShell)
scp -r E:\kali\KaliGPT user@kali-ip:/home/user/

# أو انسخ على USB وانسخه
```

### الطريقة الثالثة - نقل عبرネットワーク:
```bash
# على Kali - استقبال
nc -lvnp 9999 | tar xvz

# على Windows - إرسال
tar -cvzf - E:\kali\KaliGPT | nc kali-ip 9999
```

## 2. تشغيل Install Script
```bash
cd KaliGPT
chmod +x install.sh
sudo bash install.sh -m
```

## 3. تعيين API Key
```bash
python3 -m agents --setup-keys
# اختر "openrouter" وأدخل مفتاحك:
# YOUR_OPENROUTER_API_KEY_HERE
```

أو عدل الملف يدويًا:
```bash
nano agents/utils/api.config.json
# غير الـ api_key والمودل
```

## 4. تأكد من تثبيت أدوات Kali
```bash
sudo apt update
sudo apt install -y nmap whatweb gobuster ffuf nikto dnsrecon dirb wget curl
```

## 5. شغّل الاختبار التلقائي الكامل

### اختبار موقع واحد:
```bash
python3 kaligpt_auto_pentest.py https://www.mahanair.co.ir
```

### اختبار IP:
```bash
python3 kaligpt_auto_pentest.py http://192.168.1.1
```

### للاستخدام التفاعلي (شات):
```bash
kaligpt "ابدأ اختبار اختراق لـ https://example.com واستخدم nmap و gobuster"
# أو
python3 -m agents.openrouter "ابدأ اختبار اختراق لـ https://example.com"
```

## 6. النتائج

بعد انتهاء الاختبار، ستجد:
```
KaliGPT/pentest_output/
├── phase1_recon.json        # نتائج WhatWeb + Nmap + DNS
├── phase2_discovery.json    # Paths + Directories
├── phase3_vuln.json         # Nikto + Nmap Vuln Scripts
├── phase4_deep.json         # Sensitive paths + CORS + SQLi
├── analysis_Phase*.md       # تحليل AI لكل مرحلة
├── gobuster.txt             # نتائج Gobuster
├── nikto.json               # نتائج Nikto
└── final_report.md          # ✨ التقرير النهائي ✨
```

## ملاحظة مهمة

السكريبت `kaligpt_auto_pentest.py` يعمل كـ **Agent ذكي**:
- يشغل أدوات Kali تلقائياً (nmap, gobuster, nikto, whatweb)
- يحلل النتائج عبر AI (OpenRouter)
- يقرر الخطوات التالية بناءً على النتائج
- يولد تقرير نهائي شامل

**الفرق عن السكريبت العادي**: هذا agent حقيقي يقرر وينفذ بنفسه، مش بس يشغل أوامر
