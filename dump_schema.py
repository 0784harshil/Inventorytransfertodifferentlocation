import pyodbc

conn_str = r'DRIVER={ODBC Driver 17 for SQL Server};SERVER=HARSHIL\PCAMERICA;DATABASE=cresqlcat;Trusted_Connection=yes;'
try:
    with pyodbc.connect(conn_str) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COLUMN_NAME, IS_NULLABLE, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Inventory'")
        with open("cresqlcat_schema.txt", "w") as f:
            for row in cursor.fetchall():
                f.write(f"{row.COLUMN_NAME}, {row.IS_NULLABLE}, {row.DATA_TYPE}\n")
    print("Schema dumped to cresqlcat_schema.txt")
except Exception as e:
    print(f"Error: {e}")
