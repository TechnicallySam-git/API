from flask import Flask, jsonify, request
import os
from datetime import datetime
import pymssql


def env_or_fallback(primary_name, fallback_name=None):
    value = os.getenv(primary_name)
    if value:
        return value
    if fallback_name:
        return os.getenv(fallback_name)
    return None


SQL_CONNECTION_STRING = env_or_fallback("AZURE_SQL_CONNECTION_STRING", "SQLCONNSTR_AZURE_SQL_CONNECTION_STRING")
VALID_API_KEYS = {
    key.strip() for key in os.getenv("AZURE_API_KEYS", "").split(",") if key.strip()
}

app = Flask(__name__)
app.config['START_TIME'] = datetime.now()




#All endpoints except /api/v1/health require a valid API key passed in the request header. 
# Keys are stored in Azure App Service environment variables and never hard-coded in scripts.

def validate_api_key():
    api_key = request.headers.get('X-API-Key')
    return bool(api_key) and api_key in VALID_API_KEYS


def get_sql_connection():
    server = os.getenv("SQL_SERVER")
    user = os.getenv("SQL_USER") 
    password = os.getenv("SQL_PASSWORD")
    database = os.getenv("SQL_DATABASE")
    
    if not all([server, user, password, database]):
        raise RuntimeError("Missing one or more SQL environment variables")
    
    return pymssql.connect(
        server=server,
        user=user,
        password=password,
        database=database
    )

@app.route('/api/v1/metrics', methods=['POST'])
def add_metric():
    if not validate_api_key():
        return jsonify({"error": "Invalid or missing API key"}), 401

    data = request.get_json()
    host = data.get('host')
    cpu_usage = data.get('cpu_usage')
    memory_usage = data.get('memory_usage')

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor()
            query = "INSERT INTO metrics (host, cpu_usage, memory_usage) VALUES (?, ?, ?)"
            cursor.execute(query, (host, cpu_usage, memory_usage))
            connection.commit()
            return jsonify({"message": "Metric added successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


@app.route('/api/v1/metrics', methods=['GET'])
def get_metrics():
    if not validate_api_key():
        return jsonify({"error": "Invalid or missing API key"}), 401

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    host = request.args.get('host')

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor()
            query = "SELECT * FROM metrics WHERE timestamp BETWEEN ? AND ?"
            params = [start_date, end_date]

            if host:
                query += " AND host = ?"
                params.append(host)

            cursor.execute(query, params)
            results = cursor.fetchall()
            return jsonify([dict(row) for row in results]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/health', methods=['GET'])
def health_check():
    start_time = app.config.get('START_TIME')
    uptime_seconds = int((datetime.now() - start_time).total_seconds()) if start_time else 0
    db_status = False
    db_error = None

    try:
        conn = pymssql.connect(
            server=os.getenv("SQL_SERVER"),
            user=os.getenv("SQL_USER"),
            password=os.getenv("SQL_PASSWORD"),
            database=os.getenv("SQL_DATABASE"),
            login_timeout=5,  # 5 second timeout
            timeout=5
        )
        conn.close()
        db_status = True
    except Exception as e:
        db_error = str(e)

    return jsonify({
        "status": "healthy" if db_status else "degraded",
        "uptime_seconds": uptime_seconds,
        "db_connection": db_status,
        "db_error": db_error
    }), 200 


if __name__ == '__main__':
    # Run locally when launched with: python api.py
    app.run(host='0.0.0.0', port=5000, debug=True)
