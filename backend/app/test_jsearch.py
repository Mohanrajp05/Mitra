
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEBNINJA_API_KEY")

url = "https://api.openwebninja.com/jsearch/search-v2"

headers = {
    "x-api-key": API_KEY
}

params = {
    "query": "Python Developer jobs in Bengaluru",
    "country": "in",
    "num_pages": 1
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

print("Status:", response.status_code)
print(response.text)
