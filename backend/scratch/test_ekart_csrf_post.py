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
    
    # 1. GET Homepage to extract cookies and CSRF token
    req = urllib.request.Request(homepage_url, headers=headers)
    cookies_dict = {}
    csrf_token = ""
    
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
            cookie_headers = response.info().get_all('Set-Cookie') or []
            
            # Extract cookies using split('=', 1) to handle base64 trailing =
            for cookie in cookie_headers:
                first_part = cookie.split(';')[0]
                if '=' in first_part:
                    name, value = first_part.split('=', 1)
                    cookies_dict[name.strip()] = value.strip()
            
            # Extract CSRF token from meta tags
            meta_csrf = re.findall(r'<meta[^>]*csrf-token[^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if meta_csrf:
                csrf_token = meta_csrf[0]
                
            print("Extracted cookies:", cookies_dict)
            print("Extracted CSRF token:", csrf_token)
            
    except Exception as e:
        print("GET Homepage failed:", e)
        return
        
    if not csrf_token:
        print("Could not find CSRF token.")
        return
        
    # 2. Make POST request with CSRF token and Cookies
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
    post_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "x-csrf-token": csrf_token,
        "Referer": homepage_url,
        "Origin": "https://www.ekartlogistics.com"
    }
    
    payload = {
        "trackingId": "MY5C1314502865"
    }
    
    post_req = urllib.request.Request(
        api_url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers=post_headers, 
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(post_req, context=context, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            print("POST Status:", response.status)
            print("POST Response Body:")
            print(res_body)
    except Exception as e:
        print("POST request failed:", e)
        if hasattr(e, 'read'):
            print("Error details:", e.read().decode('utf-8'))

run_test()
