from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from flask_cors import CORS
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
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
mysql = MySQL(app)

@app.route("/", methods=['GET'])
def index():
    return "Line Bot Server is running!"

@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)  # 取得收到的訊息內容
    try:
        json_data = json.loads(body)  # json 格式化訊息內容
        access_token = os.getenv('LINE_BOT_ACCESS_TOKEN')
        secret = os.getenv('LINE_BOT_SECRET')
        line_bot_api = MessagingApi(channel_access_token=access_token)  # 使用新版 MessagingApi
        handler = WebhookHandler(channel_secret=secret)  # 使用新版 WebhookHandler
        signature = request.headers['X-Line-Signature']  # 加入回傳的 headers
        handler.handle(body, signature)  # 綁定訊息回傳的相關資訊
        tk = json_data['events'][0]['replyToken']  # 取得回傳訊息的 Token
        type = json_data['events'][0]['message']['type']  # 取得 LINE 收到的訊息類型
        if type == 'text':
            msg = json_data['events'][0]['message']['text']  # 取得 LINE 收到的文字訊息
            print(msg)  # 印出內容
            reply = msg
        else:
            reply = '你傳的不是文字呦～'
        print(reply)
        line_bot_api.reply_message(tk, TextSendMessage(reply))  # 回傳訊息
    except Exception as e:
        print(f"Error: {e}")  # 如果發生錯誤，印出錯誤訊息
    return 'OK'  # 驗證 Webhook 使用，不能省略


# LINE User API
@app.route('/line/user', methods=['POST'])
def create_line_user():
    try:
        data = request.get_json()
        if not data or 'userId' not in data:
            return jsonify({'error': '缺少必要的 userId'}), 400

        line_user_id = data.get('userId')
        display_name = data.get('displayName')
        picture_url = data.get('pictureUrl')

        cur = mysql.connection.cursor()
        try:
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
                
            mysql.connection.commit()
            return jsonify({'message': 'User created/updated successfully'}), 200
            
        except Exception as db_error:
            print(f"資料庫錯誤: {str(db_error)}")
            return jsonify({'error': '資料庫操作失敗'}), 500
        finally:
            cur.close()
            
    except Exception as e:
        print(f"處理請求時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500

# LINE 行程相關路由
@app.route('/line/trip', methods=['POST'])
def add_line_trip():
    data = request.get_json()
    line_user_id = data.get('line_user_id')
    
    try:
        cur = mysql.connection.cursor()
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
        mysql.connection.commit()
        cur.close()
        return jsonify({'message': '行程新增成功', 'trip_id': trip_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 取得行程列表
@app.route('/line/trip/<line_user_id>', methods=['GET'])
def get_line_trips(line_user_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT * FROM line_trips 
            WHERE line_user_id = %s 
            ORDER BY start_date ASC
        """, (line_user_id,))
        
        trips = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        result = [dict(zip(columns, trip)) for trip in trips]
        
        cur.close()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 刪除行程
@app.route('/line/trip/<int:trip_id>', methods=['DELETE'])
def delete_line_trip(trip_id):
    try:
        cur = mysql.connection.cursor()
        try:
            cur.execute("START TRANSACTION")
            
            cur.execute("SELECT trip_id FROM line_trips WHERE trip_id = %s", (trip_id,))
            if not cur.fetchone():
                return jsonify({'error': '找不到該行程'}), 404
            
            cur.execute("DELETE FROM line_trip_details WHERE trip_id = %s", (trip_id,))
            cur.execute("DELETE FROM line_trips WHERE trip_id = %s", (trip_id,))
            
            mysql.connection.commit()
            return jsonify({'message': '行程及其細節已成功刪除'}), 200
            
        except Exception as db_error:
            mysql.connection.rollback()
            raise db_error
            
    except Exception as e:
        print(f"刪除行程時發生錯誤: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        if cur:
            cur.close()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)