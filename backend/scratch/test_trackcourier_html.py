import urllib.request
import ssl

def check_html():
    url = "https://trackcourier.io/track-and-trace/xpressbees-logistics/14187461420018"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    context = ssl._create_unverified_context()
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            html = response.read().decode('utf-8')
            print("Response length:", len(html))
            print("Contains checkpoint:", "checkpoint" in html)
            print("Contains CCU/DDM (Kolkata):", "Kolkata" in html)
            print("Contains Delivered:", "Delivered" in html)
            
            # Let's print some lines containing Kolkata or Delivered
            for line in html.split('\n'):
                if 'kolkata' in line.lower() or 'delivered' in line.lower():
                    print(line.strip()[:200])
                    
    except Exception as e:
        print("Failed:", e)

check_html()
