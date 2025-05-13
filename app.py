from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import os
from datetime import datetime
import json

# LINE Bot SDK
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhook import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 添加新的導入
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
import urllib.parse
import time

app = Flask(__name__)
CORS(app)

# MySQL 配置
def get_db():
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST'),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        db=os.getenv('MYSQL_DB'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        ssl={'ssl': True}
    )

@app.route("/", methods=['GET'])
def index():
    return "Line Bot Server is running!"

@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        access_token = os.getenv('LINE_BOT_ACCESS_TOKEN')
        secret = os.getenv('LINE_BOT_SECRET')
        line_bot_api = MessagingApi(channel_access_token=access_token)
        handler = WebhookHandler(channel_secret=secret)
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)
        tk = json_data['events'][0]['replyToken']
        type = json_data['events'][0]['message']['type']
        if type == 'text':
            msg = json_data['events'][0]['message']['text']
            print(msg)
            reply = msg
        else:
            reply = '你傳的不是文字呦～'
        print(reply)
        line_bot_api.reply_message(tk, TextSendMessage(reply))
    except Exception as e:
        print(f"Error: {e}")
    return 'OK'

@app.route('/line/user', methods=['POST'])
def create_line_user():
    try:
        data = request.get_json()
        if not data or 'userId' not in data:
            return jsonify({'error': '缺少必要的 userId'}), 400

        line_user_id = data.get('userId')
        display_name = data.get('displayName')
        picture_url = data.get('pictureUrl')

        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute("SELECT line_user_id FROM line_users WHERE line_user_id = %s", (line_user_id,))
                existing_user = cur.fetchone()
                
                if not existing_user:
                    cur.execute("""
                        INSERT INTO line_users (line_user_id, display_name, picture_url)
                        VALUES (%s, %s, %s)
                    """, (line_user_id, display_name, picture_url))
                else:
                    cur.execute("""
                        UPDATE line_users 
                        SET display_name = %s, picture_url = %s
                        WHERE line_user_id = %s
                    """, (display_name, picture_url, line_user_id))
                    
                db.commit()
                return jsonify({'message': 'User created/updated successfully'}), 200
                
        except Exception as db_error:
            print(f"資料庫錯誤: {str(db_error)}")
            return jsonify({'error': '資料庫操作失敗'}), 500
        finally:
            db.close()
            
    except Exception as e:
        print(f"處理請求時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/line/trip', methods=['POST'])
def add_line_trip():
    try:
        data = request.get_json()
        print(f"接收到的資料: {data}")  # 印出接收到的資料
        
        if not data:
            return jsonify({'error': '未接收到資料'}), 400
            
        line_user_id = data.get('line_user_id')
        if not line_user_id:
            return jsonify({'error': '缺少 line_user_id'}), 400
        
        required_fields = ['title', 'start_date', 'end_date', 'area']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({'error': f'缺少必要欄位: {", ".join(missing_fields)}'}), 400
    
        db = get_db()
        try:
            with db.cursor() as cur:
                print(f"準備執行 SQL 插入...")  # 印出執行狀態
                cur.execute("""
                    INSERT INTO line_trips 
                    (line_user_id, title, description, start_date, end_date, area)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    line_user_id,
                    data.get('title'),
                    data.get('description'),
                    data.get('start_date'),
                    data.get('end_date'),
                    data.get('area')
                ))
                
                trip_id = cur.lastrowid
                db.commit()
                print(f"成功新增行程，ID: {trip_id}")  # 印出成功訊息
                return jsonify({'message': '行程新增成功', 'trip_id': trip_id}), 201
        except Exception as db_error:
            print(f"資料庫錯誤: {str(db_error)}")  # 印出資料庫錯誤
            return jsonify({'error': f'資料庫錯誤: {str(db_error)}'}), 500
        finally:
            db.close()
            
    except Exception as e:
        print(f"處理請求時發生錯誤: {str(e)}")  # 印出一般錯誤
        return jsonify({'error': str(e)}), 500

@app.route('/line/trip/<line_user_id>', methods=['GET'])
def get_line_trips(line_user_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT * FROM line_trips 
                WHERE line_user_id = %s 
                ORDER BY start_date ASC
            """, (line_user_id,))
            
            result = cur.fetchall()
            return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/line/trip/<int:trip_id>', methods=['DELETE'])
def delete_line_trip(trip_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("START TRANSACTION")
            
            cur.execute("SELECT trip_id FROM line_trips WHERE trip_id = %s", (trip_id,))
            if not cur.fetchone():
                return jsonify({'error': '找不到該行程'}), 404
            
            cur.execute("DELETE FROM line_trip_details WHERE trip_id = %s", (trip_id,))
            cur.execute("DELETE FROM line_trips WHERE trip_id = %s", (trip_id,))
            
            db.commit()
            return jsonify({'message': '行程及其細節已成功刪除'}), 200
            
    except Exception as e:
        db.rollback()
        print(f"刪除行程時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# LINE 行程細節相關路由
@app.route('/line/trip_detail', methods=['POST'])
def add_line_trip_detail():
    data = request.get_json()
    trip_id = data.get('trip_id')
    location = data.get('location')
    date = data.get('date')
    start_time = data.get('start_time')
    end_time = data.get('end_time')

    if not all([trip_id, location, date, start_time, end_time]):
        return jsonify({'error': '缺少必要欄位'}), 400

    db = get_db()
    try:
        with db.cursor() as cur:
            # 檢查行程是否存在
            cur.execute("SELECT start_date, end_date FROM line_trips WHERE trip_id = %s", (trip_id,))
            trip = cur.fetchone()
            if not trip:
                return jsonify({'error': '找不到對應的行程'}), 404
                
            # 檢查日期是否在行程範圍內
            detail_date = datetime.strptime(date, '%Y-%m-%d').date()
            trip_start = trip['start_date']
            trip_end = trip['end_date']
            
            if detail_date < trip_start or detail_date > trip_end:
                return jsonify({
                    'error': '行程細節的日期必須在行程的日期範圍內',
                    'valid_range': {
                        'start_date': trip_start.strftime('%Y-%m-%d'),
                        'end_date': trip_end.strftime('%Y-%m-%d')
                    }
                }), 400

            # 新增行程細節
            cur.execute("""
                INSERT INTO line_trip_details 
                (trip_id, location, date, start_time, end_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (trip_id, location, date, start_time, end_time))
            
            detail_id = cur.lastrowid
            db.commit()
            
            return jsonify({
                'message': '行程細節新增成功',
                'detail_id': detail_id
            }), 201
            
    except Exception as e:
        print(f"新增行程細節時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route('/line/trip_detail/<int:trip_id>', methods=['GET'])
def get_line_trip_details(trip_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            # 先檢查行程是否存在
            cur.execute("SELECT trip_id FROM line_trips WHERE trip_id = %s", (trip_id,))
            if not cur.fetchone():
                return jsonify({'error': '找不到該行程'}), 404
                
            # 獲取行程細節
            cur.execute("""
                SELECT 
                    detail_id, 
                    trip_id, 
                    location, 
                    DATE_FORMAT(date, '%%Y-%%m-%%d') as date,
                    TIME_FORMAT(start_time, '%%H:%%i') as start_time,
                    TIME_FORMAT(end_time, '%%H:%%i') as end_time
                FROM line_trip_details 
                WHERE trip_id = %s 
                ORDER BY date ASC, start_time ASC
            """, (trip_id,))
            
            result = cur.fetchall()
            
            # 確保結果可序列化
            serializable_result = []
            for item in result:
                serializable_item = {
                    'detail_id': item['detail_id'],
                    'trip_id': item['trip_id'],
                    'location': item['location'],
                    'date': item['date'],
                    'start_time': item['start_time'],
                    'end_time': item['end_time']
                }
                serializable_result.append(serializable_item)
            
            return jsonify(serializable_result if serializable_result else []), 200
            
    except Exception as e:
        print(f"獲取行程細節時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# 刪除單一行程細節
@app.route('/line/trip_detail/<int:detail_id>', methods=['DELETE'])
def delete_line_trip_detail(detail_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            # 先確認該細節是否存在
            cur.execute("SELECT detail_id FROM line_trip_details WHERE detail_id = %s", (detail_id,))
            if not cur.fetchone():
                return jsonify({'error': '找不到該行程細節'}), 404
                
            cur.execute("DELETE FROM line_trip_details WHERE detail_id = %s", (detail_id,))
            db.commit()
            return jsonify({'message': '行程細節刪除成功'}), 200
    except Exception as e:
        print(f"刪除行程細節時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# 緩存存儲
cache = {}
CACHE_EXPIRY = 3600  # 緩存過期時間（秒）

def get_cache_key(search_params, page):
    """生成緩存鍵"""
    key_parts = [
        search_params['location'],
        search_params['startDate'],
        search_params.get('endDate', search_params['startDate']),
        f"{search_params['startTimeHour']}:{search_params['startTimeMin']}",
        f"{search_params['endTimeHour']}:{search_params['endTimeMin']}",
        search_params['bagSize'],
        search_params['suitcaseSize'],
        str(page)
    ]
    return "_".join(key_parts)

def scrape_lockers(search_params, page=1, per_page=5):
    """爬取寄物櫃資訊 - 使用 requests"""
    try:
        # 使用 geopy 解析地址
        geolocator = Nominatim(user_agent="my_geocoder")
        location_data = geolocator.geocode(search_params['location'])
        
        if not location_data:
            return {'error': '無法找到該地點'}
        
        # 構建搜尋 URL
        base_url = "https://cloak.ecbo.io/zh-TW/locations"
        params = {
            'name': search_params['location'],
            'startDate': search_params['startDate'],
            'endDate': search_params.get('endDate', search_params['startDate']),
            'startDateTimeHour': search_params['startTimeHour'],
            'startDateTimeMin': search_params['startTimeMin'],
            'endDateTimeHour': search_params['endTimeHour'],
            'endDateTimeMin': search_params['endTimeMin'],
            'bagSize': search_params['bagSize'],
            'suitcaseSize': search_params['suitcaseSize'],
            'lat': location_data.latitude,
            'lon': location_data.longitude,
            'page': page
        }
        
        # 發送請求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        
        # 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        cards = soup.find_all('li', class_='SpaceCard_space__YnURE')
        
        # 解析結果
        results = []
        for card in cards[(page-1)*per_page:page*per_page]:
            try:
                name_element = card.find('strong', class_='SpaceCard_nameText__308Dp')
                category_element = card.find('div', class_='SpaceCard_category__2rx7q')
                rating_element = card.find('span', class_='SpaceCard_ratingPoint__2CaOa')
                suitcase_price_element = card.find('span', class_='SpaceCard_priceCarry__3Owgr')
                bag_price_element = card.find('span', class_='SpaceCard_priceBag__Bv_Oz')
                image_element = card.find('img')
                link_element = card.find('a', class_='SpaceCard_spaceLink__2MeRc')
                
                result = {
                    'name': name_element.text.strip() if name_element else '未知名稱',
                    'category': category_element.text.strip() if category_element else '未分類',
                    'rating': rating_element.text.strip() if rating_element else 'N/A',
                    'suitcase_price': suitcase_price_element.text.strip() if suitcase_price_element else '價格未知',
                    'bag_price': bag_price_element.text.strip() if bag_price_element else '價格未知',
                    'image_url': image_element['src'] if image_element and 'src' in image_element.attrs else '',
                    'link': f"https://cloak.ecbo.io{link_element['href']}" if link_element else '#'
                }
                results.append(result)
            except Exception as e:
                print(f"解析卡片時發生錯誤: {str(e)}")
                continue
        
        total_items = len(cards)
        total_pages = (total_items + per_page - 1) // per_page
        
        return {
            'results': results,
            'pagination': {
                'current_page': page,
                'total_pages': total_pages,
                'total_items': total_items,
                'per_page': per_page
            }
        }
        
    except Exception as e:
        print(f"爬蟲錯誤: {str(e)}")
        return {'error': str(e)}

@app.route('/search-lockers', methods=['POST'])
def search_lockers():
    try:
        data = request.get_json()
        page = int(data.get('page', 1))
        per_page = int(data.get('per_page', 5))
        
        # 驗證必要欄位
        required_fields = ['location', 'startDate', 'startTimeHour', 
                         'startTimeMin', 'endTimeHour', 'endTimeMin']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'error': f'缺少必要欄位: {field}',
                    'received_data': data
                }), 400
        
        # 設置默認值
        data.setdefault('bagSize', '0')
        data.setdefault('suitcaseSize', '0')
        data.setdefault('endDate', data['startDate'])
        
        # 檢查緩存
        cache_key = get_cache_key(data, page)
        current_time = datetime.now().timestamp()
        
        if cache_key in cache and (current_time - cache[cache_key]['timestamp']) < CACHE_EXPIRY:
            return jsonify(cache[cache_key]['data']), 200
        
        # 爬取數據
        results = scrape_lockers(data, page, per_page)
        
        if 'error' in results:
            return jsonify(results), 400
        
        # 保存到緩存
        cache[cache_key] = {
            'data': results,
            'timestamp': current_time
        }
        
        return jsonify(results), 200
        
    except Exception as e:
        print(f"API error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)