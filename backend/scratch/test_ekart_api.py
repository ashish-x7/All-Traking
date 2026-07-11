import urllib.request
import json
import ssl

def test_ekart():
    url = "https://ekartlogistics.com/ws/getTrackingDetails"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    # Try with a real AWB
    payload = {
        "trackingId": "MY5C1314502865"
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
    context = ssl._create_unverified_context()
    
    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as response:
            res_body = response.read().decode()
            print("Response Code:", response.status)
            print("Response Headers:", dict(response.info()))
            print("Response Body (first 1000 chars):")
            print(res_body[:1000])
    except Exception as e:
        print("API failed:", e)

test_ekart()
