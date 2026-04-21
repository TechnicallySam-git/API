from flask import Flask, jsonify, request
import os
from datetime import datetime, timezone
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
        return jsonify({"status": "error", "message": "Unauthorized. Valid X-API-Key required."}), 401

    data = request.get_json()
    host = data.get('host')
    ip = data.get('ip')
    metrics = data.get('metrics', {})  #
    cpu_usage = metrics.get('cpu_usage')
    mem_used_mb = metrics.get('mem_used_mb')
    disk_free_gb = metrics.get('disk_free_gb')
    timestamp = data.get('timestamp')

    if not host:
        return jsonify({"status": "error", "message": "Missing required field: host"}), 400
    if not ip:
        return jsonify({"status": "error", "message": "Missing required field: ip"}), 400
    if cpu_usage is None:
        return jsonify({"status": "error", "message": "Missing required field: cpu_usage"}), 400
    if mem_used_mb is None:
        return jsonify({"status": "error", "message": "Missing required field: mem_used_mb"}), 400
    if disk_free_gb is None:
        return jsonify({"status": "error", "message": "Missing required field: disk_free_gb"}), 400
    if not timestamp:
        return jsonify({"status": "error", "message": "Missing required field: timestamp"}), 400

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor()
            query = """
                INSERT INTO server_metrics (host, ip, cpu_usage, mem_used_mb, disk_free_gb, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (host, ip, cpu_usage, mem_used_mb, disk_free_gb, timestamp))
            connection.commit()
            return jsonify({
                "status": "success",
                "message": "Metrics recorded successfully.",
                "host": host,
                "timestamp": timestamp
            }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/metrics', methods=['GET'])
def get_metrics():
    if not validate_api_key():
        return jsonify({"status": "error", "message": "Unauthorized. Valid X-API-Key required."}), 401

    
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    host = request.args.get('host')
    limit = request.args.get('limit', 100, type=int)

    if limit > 1000:
        limit = 1000

    try:
        with get_sql_connection() as connection:
            cursor = connection.cursor(as_dict=True)

            if from_date and to_date:
                query = "SELECT TOP (%s) * FROM server_metrics WHERE timestamp BETWEEN %s AND %s"
                params = [limit, from_date, to_date]
            else:
                query = "SELECT TOP (%s) * FROM server_metrics"
                params = [limit]

            if host:
                if from_date and to_date:
                    query += " AND host = %s"
                else:
                    query += " WHERE host = %s"
                params.append(host)

            query += " ORDER BY timestamp DESC"
            cursor.execute(query, params)
            results = cursor.fetchall()

            if not results:
                return jsonify({"status": "error", "message": "No records match the filter."}), 404

            return jsonify({
                "status": "success",
                "count": len(results),
                "results": results
            }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/health', methods=['GET'])
def health_check():
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
        "api": "online",
        "database": "connected" if db_status else "unreachable",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)