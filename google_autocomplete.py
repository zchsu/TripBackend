import os
import requests

def handler(request):
    input_text = request.args.get('input')
    language = request.args.get('language', 'zh-TW')
    components = request.args.get('components', 'country:tw')
    key = os.environ.get('GOOGLE_MAPS_API_KEY')
    url = f'https://maps.googleapis.com/maps/api/place/autocomplete/json?input={input_text}&language={language}&components={components}&key={key}'
    r = requests.get(url)
    return r.json()