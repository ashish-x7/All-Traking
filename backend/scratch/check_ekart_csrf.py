import urllib.request
import re
import ssl

def check_csrf():
    url = "https://www.ekartlogistics.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    req = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context()
    
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
            cookies = response.info().get_all('Set-Cookie')
            print("Set-Cookie:", cookies)
            
            # Find any script tags containing csrf or tokens
            csrf_matches = re.findall(r'csrfToken\s*:\s*["\']([^"\']+)["\']', html)
            print("Found csrfToken in JSON:", csrf_matches)
            
            # Let's search general 'csrf' or 'token'
            all_tokens = re.findall(r'csrf[a-zA-Z]*\s*[:=]\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
            print("Found other csrf/tokens:", all_tokens)
            
            # Let's search for meta tags
            meta_csrf = re.findall(r'<meta[^>]*csrf-token[^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            print("Meta csrf:", meta_csrf)
            meta_csrf_alt = re.findall(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*csrf-token', html, re.IGNORECASE)
            print("Meta csrf Alt:", meta_csrf_alt)
            
    except Exception as e:
        print("Failed:", e)

check_csrf()
