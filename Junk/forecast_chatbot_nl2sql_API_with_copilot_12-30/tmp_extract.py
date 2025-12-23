from db import _extract_table_names
sql = """SELECT substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) AS date, SUM(Revenue) AS total_revenue, AVG(Revenue) AS avg_revenue FROM Revenue_data WHERE substr(Datetime,7,4) || '-' || substr(Datetime,4,2) || '-' || substr(Datetime,1,2) = '2015-12-11' GROUP BY date;"""
print(_extract_table_names(sql))
