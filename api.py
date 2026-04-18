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
    ip = data.get('ip')
    cpu_usage = data.get('cpu_usage')
    mem_used_mb = data.get('mem_used_mb')
    disk_free_gb = data.get('disk_free_gb')
    timestamp = data.get('timestamp')

    if not all([host, ip, cpu_usage is not None, mem_used_mb is not None, disk_free_gb is not None, timestamp]):
        return jsonify({"error": "Missing required fields"}), 400

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor()
            query = """
                INSERT INTO server_metrics (host, ip, cpu_usage, mem_used_mb, disk_free_gb, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (host, ip, cpu_usage, mem_used_mb, disk_free_gb, timestamp))
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

    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date are required"}), 400

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor(as_dict=True)
            query = "SELECT * FROM server_metrics WHERE timestamp BETWEEN %s AND %s"
            params = [start_date, end_date]

            if host:
                query += " AND host = %s"
                params.append(host)

            cursor.execute(query, params)
            results = cursor.fetchall()
            return jsonify(results), 200

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
            login_timeout=5,
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
    app.run(host='0.0.0.0', port=5000, debug=True)