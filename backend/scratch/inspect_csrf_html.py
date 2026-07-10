import urllib.request
import ssl

def inspect_html():
    homepage_url = "https://www.ekartlogistics.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    context = ssl._create_unverified_context()
    
    req = urllib.request.Request(homepage_url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
            for line in html.split('\n'):
                if 'csrf' in line.lower() or 'token' in line.lower():
                    print(line.strip())
    except Exception as e:
        print("Failed:", e)

inspect_html()
