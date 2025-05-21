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

# test route
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

# get user info
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

# insert trip
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

# get trip list by user id
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

# delete trip
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

# insert trip detail
@app.route('/line/trip_detail', methods=['POST'])
def add_line_trip_detail():
    data = request.get_json()
    
    # 檢查必要欄位
    required_fields = ['trip_id', 'location', 'date', 'start_time', 'end_time']
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return jsonify({
            'error': f'缺少必要欄位: {", ".join(missing_fields)}'
        }), 400

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

# get trip detail by trip id
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

# delete trip detail
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

# update trip
@app.route('/line/trip/<int:trip_id>', methods=['PUT'])
def update_line_trip(trip_id):
    try:
        data = request.get_json()
        db = get_db()
        
        with db.cursor() as cur:
            # 檢查行程是否存在
            cur.execute("SELECT trip_id FROM line_trips WHERE trip_id = %s", (trip_id,))
            if not cur.fetchone():
                return jsonify({'error': '找不到該行程'}), 404

            # 更新行程
            cur.execute("""
                UPDATE line_trips 
                SET title = %s, description = %s, start_date = %s, 
                    end_date = %s, area = %s
                WHERE trip_id = %s
            """, (
                data.get('title'),
                data.get('description'),
                data.get('start_date'),
                data.get('end_date'),
                data.get('area'),
                trip_id
            ))
            
            db.commit()
            return jsonify({'message': '行程更新成功'}), 200
            
    except Exception as e:
        print(f"更新行程時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# update trip detail
@app.route('/line/trip_detail/<int:detail_id>', methods=['PUT'])
def update_line_trip_detail(detail_id):
    try:
        data = request.get_json()
        db = get_db()
        
        with db.cursor() as cur:
            # 檢查細節是否存在
            cur.execute("""
                SELECT d.detail_id, t.start_date, t.end_date 
                FROM line_trip_details d
                JOIN line_trips t ON d.trip_id = t.trip_id
                WHERE d.detail_id = %s
            """, (detail_id,))
            
            result = cur.fetchone()
            if not result:
                return jsonify({'error': '找不到該行程細節'}), 404

            # 檢查日期是否在行程範圍內
            detail_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            trip_start = result['start_date']
            trip_end = result['end_date']
            
            if detail_date < trip_start or detail_date > trip_end:
                return jsonify({
                    'error': '行程細節的日期必須在行程的日期範圍內',
                    'valid_range': {
                        'start_date': trip_start.strftime('%Y-%m-%d'),
                        'end_date': trip_end.strftime('%Y-%m-%d')
                    }
                }), 400

            # 更新行程細節
            cur.execute("""
                UPDATE line_trip_details 
                SET location = %s, date = %s, start_time = %s, end_time = %s
                WHERE detail_id = %s
            """, (
                data['location'],
                data['date'],
                data['start_time'],
                data['end_time'],
                detail_id
            ))
            
            db.commit()
            return jsonify({'message': '行程細節更新成功'}), 200
            
    except Exception as e:
        print(f"更新行程細節時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

    # 新增分享行程的路由
    @app.route('/line/trip/share', methods=['POST'])
    def share_trip():
        try:
            data = request.get_json()
            trip_id = data.get('trip_id')
            shared_user_id = data.get('shared_user_id')
            
            if not all([trip_id, shared_user_id]):
                return jsonify({'error': '缺少必要參數'}), 400

            db = get_db()
            try:
                with db.cursor() as cur:
                    # 先確認行程存在
                    cur.execute("SELECT trip_id FROM line_trips WHERE trip_id = %s", (trip_id,))
                    if not cur.fetchone():
                        return jsonify({'error': '找不到該行程'}), 404

                    # 新增或更新共享記錄
                    cur.execute("""
                        INSERT INTO line_trip_collaborators 
                        (trip_id, shared_user_id, created_at)
                        VALUES (%s, %s, NOW())
                        ON DUPLICATE KEY UPDATE updated_at = NOW()
                    """, (trip_id, shared_user_id))
                    
                    db.commit()
                    return jsonify({'message': '分享成功'}), 200

            except Exception as db_error:
                print(f"資料庫錯誤: {str(db_error)}")
                return jsonify({'error': f'資料庫錯誤: {str(db_error)}'}), 500
            finally:
                db.close()

        except Exception as e:
            print(f"分享行程時發生錯誤: {str(e)}")
            return jsonify({'error': str(e)}), 500
        
    # 獲取用戶的行程和分享給他的行程   
    @app.route('/line/trip/<line_user_id>', methods=['GET'])
    def get_line_trips(line_user_id):
            db = get_db()
            try:
                with db.cursor() as cur:
                    # 獲取用戶自己的行程和分享給他的行程
                    cur.execute("""
                        SELECT DISTINCT t.* 
                        FROM line_trips t
                        LEFT JOIN line_trip_collaborators c ON t.trip_id = c.trip_id
                        WHERE t.line_user_id = %s 
                        OR c.shared_user_id = %s
                        ORDER BY t.start_date ASC
                    """, (line_user_id, line_user_id))
                    
                    result = cur.fetchall()
                    return jsonify(result), 200
            except Exception as e:
                return jsonify({'error': str(e)}), 500
            finally:
                db.close()    

    

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)