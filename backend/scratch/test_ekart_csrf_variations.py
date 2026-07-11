import urllib.request
import re
import json
import ssl

def run_test():
    homepage_url = "https://www.ekartlogistics.com/"
    api_url = "https://www.ekartlogistics.com/ws/getTrackingDetails"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    context = ssl._create_unverified_context()
    
    # GET homepage
    req = urllib.request.Request(homepage_url, headers=headers)
    cookies_dict = {}
    csrf_token = ""
    
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
            cookie_headers = response.info().get_all('Set-Cookie') or []
            for cookie in cookie_headers:
                first_part = cookie.split(';')[0]
                if '=' in first_part:
                    name, value = first_part.split('=', 1)
                    cookies_dict[name.strip()] = value.strip()
            
            meta_csrf = re.findall(r'<meta[^>]*csrf-token[^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if meta_csrf:
                csrf_token = meta_csrf[0]
    except Exception as e:
        print("GET failed:", e)
        return
        
    print("Found CSRF:", csrf_token)
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
    
    # Let's test payload with _csrf
    post_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Referer": homepage_url,
        "Origin": "https://www.ekartlogistics.com"
    }
    
    # 1. Test body parameter _csrf
    payload1 = {
        "trackingId": "MY5C1314502865",
        "_csrf": csrf_token
    }
    
    print("\n--- Testing body _csrf ---")
    try:
        post_req = urllib.request.Request(api_url, data=json.dumps(payload1).encode('utf-8'), headers=post_headers, method="POST")
        with urllib.request.urlopen(post_req, context=context, timeout=10) as response:
            print("Status:", response.status)
            print("Body:", response.read().decode('utf-8'))
    except Exception as e:
        if hasattr(e, 'read'):
            print("Failed:", e.read().decode('utf-8'))
        else:
            print("Failed:", e)
            
    # 2. Test header X-XSRF-TOKEN
    headers2 = post_headers.copy()
    headers2["X-XSRF-TOKEN"] = csrf_token
    payload2 = {
        "trackingId": "MY5C1314502865"
    }
    print("\n--- Testing X-XSRF-TOKEN header ---")
    try:
        post_req = urllib.request.Request(api_url, data=json.dumps(payload2).encode('utf-8'), headers=headers2, method="POST")
        with urllib.request.urlopen(post_req, context=context, timeout=10) as response:
            print("Status:", response.status)
            print("Body:", response.read().decode('utf-8'))
    except Exception as e:
        if hasattr(e, 'read'):
            print("Failed:", e.read().decode('utf-8'))
        else:
            print("Failed:", e)

run_test()
