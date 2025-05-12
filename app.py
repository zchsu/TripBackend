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
    data = request.get_json()
    line_user_id = data.get('line_user_id')
    
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO line_trips 
                (line_user_id, title, description, start_date, end_date, area, tags, budget, preferred_gender)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                line_user_id,
                data.get('title'),
                data.get('description'),
                data.get('start_date'),
                data.get('end_date'),
                data.get('area'),
                data.get('tags'),
                data.get('budget'),
                data.get('preferred_gender', 'any')
            ))
            
            trip_id = cur.lastrowid
            db.commit()
            return jsonify({'message': '行程新增成功', 'trip_id': trip_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

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
                SELECT detail_id, trip_id, location, 
                       DATE_FORMAT(date, %%Y-%%m-%%d) as date,
                       TIME_FORMAT(start_time, %%H:%%i) as start_time,
                       TIME_FORMAT(end_time, %%H:%%i) as end_time
                FROM line_trip_details 
                WHERE trip_id = %s 
                ORDER BY date ASC, start_time ASC
            """, (trip_id,))
            
            result = cur.fetchall()
            return jsonify(result if result else []), 200
            
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

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)