from flask import Flask, render_template, jsonify, request
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG

app = Flask(__name__)
app.config.from_pyfile('config.py')

# Database connection function
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# Home page route
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/question1')
def question1():
    return render_template('question1.html')

@app.route('/question2')
def question2():
    return render_template('question2.html')

@app.route('/question3')
def question3():
    return render_template('question3.html')

# Question 1: Get polling units
@app.route('/api/polling-units')
def get_polling_units():
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    cursor.execute("""
        SELECT uniqueid, polling_unit_name, polling_unit_number 
        FROM polling_unit 
        WHERE lga_id IN (SELECT lga_id FROM lga WHERE state_id = 25)
        AND uniqueid > 0
        AND polling_unit_name IS NOT NULL
        ORDER BY polling_unit_name 
        LIMIT 200
    """)
    
    units = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return jsonify(units)

# Question 1: Get polling unit results
@app.route('/api/polling-unit-results/<int:pu_id>')
def get_polling_unit_results(pu_id):
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    
    # Get polling unit info
    cursor.execute("SELECT uniqueid, polling_unit_name FROM polling_unit WHERE uniqueid = %s", (pu_id,))
    polling_unit = cursor.fetchone()
    
    # Get results
    cursor.execute("""
        SELECT party_abbreviation, party_score 
        FROM announced_pu_results 
        WHERE polling_unit_uniqueid = %s
        ORDER BY party_score DESC
    """, (str(pu_id),))
    
    results = cursor.fetchall()
    cursor.close()
    connection.close()
    
    if not results:
        return jsonify({'error': 'No results found for this polling unit'}), 404
    
    return jsonify({
        'polling_unit_id': pu_id,
        'polling_unit_name': polling_unit['polling_unit_name'] if polling_unit else 'Unknown',
        'results': results
    })

# Question 2: Get LGAs
@app.route('/api/lgas')
def get_lgas():
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT lga_id, lga_name FROM lga WHERE state_id = 25 ORDER BY lga_name")
    lgas = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return jsonify(lgas)

# Question 2: Get LGA summary (summed results from polling units)
@app.route('/api/lga-summary/<int:lga_id>')
def get_lga_summary(lga_id):
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    
    # Get LGA name
    cursor.execute("SELECT lga_name FROM lga WHERE lga_id = %s", (lga_id,))
    lga = cursor.fetchone()
    
    # Count polling units under this LGA
    cursor.execute("""
        SELECT COUNT(DISTINCT pu.uniqueid) as count
        FROM polling_unit pu
        JOIN ward w ON pu.ward_id = w.uniqueid
        WHERE w.lga_id = %s
    """, (lga_id,))
    count_data = cursor.fetchone()
    
    # SUMMED RESULTS from polling units (NOT from announced_lga_results)
    cursor.execute("""
        SELECT 
            apr.party_abbreviation,
            SUM(CAST(apr.party_score AS UNSIGNED)) as total
        FROM announced_pu_results apr
        JOIN polling_unit pu ON apr.polling_unit_uniqueid = pu.uniqueid
        JOIN ward w ON pu.ward_id = w.uniqueid
        WHERE w.lga_id = %s
        GROUP BY apr.party_abbreviation
        ORDER BY total DESC
    """, (lga_id,))
    
    summed_results = cursor.fetchall()
    summed_total = sum(int(r['total']) for r in summed_results)
    
    # OFFICIAL LGA RESULTS (for comparison)
    cursor.execute("""
        SELECT party_abbreviation, party_score 
        FROM announced_lga_results 
        WHERE lga_name = %s
        ORDER BY party_score DESC
    """, (str(lga_id),))
    
    official_results = cursor.fetchall()
    official_total = sum(int(r['party_score']) for r in official_results)
    
    cursor.close()
    connection.close()
    
    return jsonify({
        'lga_name': lga['lga_name'],
        'polling_units_count': count_data['count'],
        'summed_results': summed_results,
        'summed_total': summed_total,
        'official_results': official_results,
        'official_total': official_total
    })

# Question 3: Get parties list
@app.route('/api/parties')
def get_parties():
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT partyid, partyname FROM party ORDER BY partyid")
    parties = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return jsonify(parties)

# Question 3: Save new results
@app.route('/api/save-results', methods=['POST'])
def save_results():
    try:
        data = request.json
        print("Received data:", data)  # Debug log
        
        polling_unit_id = data.get('polling_unit_id')
        entered_by = data.get('entered_by')
        party_scores = data.get('party_scores', {})
        
        # Validation
        if not polling_unit_id:
            return jsonify({'success': False, 'message': 'Please select a polling unit'}), 400
        
        if not entered_by:
            return jsonify({'success': False, 'message': 'Please enter your name'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'message': 'Database connection failed'}), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Verify polling unit exists
        cursor.execute("SELECT uniqueid FROM polling_unit WHERE uniqueid = %s", (polling_unit_id,))
        pu_check = cursor.fetchone()
        
        if not pu_check:
            cursor.close()
            connection.close()
            return jsonify({'success': False, 'message': f'Polling unit {polling_unit_id} does not exist'}), 400
        
        # Check if results already exist (polling_unit_uniqueid is VARCHAR in database)
        cursor.execute("SELECT COUNT(*) as count FROM announced_pu_results WHERE polling_unit_uniqueid = %s", (str(polling_unit_id),))
        check = cursor.fetchone()
        
        if check['count'] > 0:
            cursor.close()
            connection.close()
            return jsonify({'success': False, 'message': 'Results already exist for this polling unit'}), 400
        
        from datetime import datetime
        date_entered = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        success_count = 0
        inserted_parties = []
        
        for party, score in party_scores.items():
            score = int(score)
            if score > 0:
                try:
                    cursor.execute("""
                        INSERT INTO announced_pu_results 
                        (polling_unit_uniqueid, party_abbreviation, party_score, 
                         entered_by_user, date_entered, user_ip_address)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (str(polling_unit_id), party, score, entered_by, date_entered, '127.0.0.1'))
                    success_count += 1
                    inserted_parties.append(party)
                    print(f"Inserted {party}: {score}")  # Debug log
                except Exception as e:
                    print(f"Error inserting {party}: {e}")  # Debug log
        
        connection.commit()
        cursor.close()
        connection.close()
        
        if success_count > 0:
            return jsonify({'success': True, 'message': f'✅ Successfully saved results for {success_count} parties: {", ".join(inserted_parties)}'})
        else:
            return jsonify({'success': False, 'message': 'No valid scores to save. Please enter at least one score greater than 0.'}), 400
            
    except Exception as e:
        print(f"Exception in save_results: {e}")  # Debug log
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

