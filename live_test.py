import json
import requests
import sys
sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)

BASE = "https://www.mahanair.co.ir"
CONTENT = "https://content.mahanair.co.ir"
AUTH = "https://id.mahanair.co.ir"
GKEY = "AIzaSyAmTTWaMMMJEB2CB4hVu9GCnVBTauue6_A"

results = []

def test(name, fn):
    try:
        r = fn()
        results.append({"test": name, "success": True, "result": r})
        print(f"[+] {name}: {r[:200] if isinstance(r, str) else r}")
    except Exception as e:
        results.append({"test": name, "success": False, "result": str(e)})
        print(f"[-] {name}: ERROR - {e}")

# 1. GraphQL Introspection
test("GraphQL Introspection", lambda: requests.post(f"{CONTENT}/api/graphql", json={"query": "{__schema{types{name,kind,fields{name,type{name}}}}}"}, timeout=15).json())

# 2. Google Maps API Key
test("Google Maps API Key", lambda: requests.get(f"https://maps.googleapis.com/maps/api/geocode/json?address=Tehran&key={GKEY}", timeout=10).json())

# 3. Client Settings (Unauthenticated)
test("Client Settings", lambda: requests.get(f"{BASE}/api/client/setting", timeout=10).json())

# 4. CORS Test
test("CORS Preflight", lambda: requests.options(f"{BASE}/api/client/setting", headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "GET"}, timeout=10).headers.get("Access-Control-Allow-Origin", "Not set"))

# 5. Security Headers
test("Security Headers", lambda: {k: v for k,v in dict(requests.get(BASE, timeout=10).headers).items() if k.lower().startswith("x-") or k.lower() == "strict-transport-security"})

# 6. OAuth OpenID Config
test("OIDC Config", lambda: requests.get(f"{AUTH}/.well-known/openid-configuration", timeout=10).json())

# 7. GraphQL Query test
test("GraphQL Query setting", lambda: requests.post(f"{CONTENT}/api/graphql", json={"query": "{setting{env clientId issuer redirectUrl gMapCode captchaEnable}}"}, timeout=15).json())

# 8. Robots.txt
test("Robots.txt", lambda: requests.get(f"{BASE}/robots.txt", timeout=10).text)

print("\n===== ALL RESULTS =====")
print(json.dumps(results, indent=2, ensure_ascii=False))
