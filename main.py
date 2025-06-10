from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import io 


app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here' 


UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 


NUM_OTHER_MATCHES = 5 
TOP_MATCH_THRESHOLD = 65

def compute_match_score(username, employee_name, first_name, last_name, emp_id):

    numbers_in_username = re.findall(r'\d+', username)
    number_match_bonus = 0
    if numbers_in_username:
       
        if str(emp_id) in numbers_in_username:
            number_match_bonus = 20 
    
    lev_full = fuzz.ratio(username, employee_name)
    partial_full = fuzz.partial_ratio(username, employee_name)
    token_set_full = fuzz.token_set_ratio(username, employee_name)
    

    lev_first = fuzz.ratio(username, first_name)
    partial_first = fuzz.partial_ratio(username, first_name)
    token_set_first = fuzz.token_set_ratio(username, first_name)
    
    
    lev_last = fuzz.ratio(username, last_name)
    partial_last = fuzz.partial_ratio(username, last_name)
    token_set_last = fuzz.token_set_ratio(username, last_name)
    
    
    soundex_match_last = int(jellyfish.soundex(username) == jellyfish.soundex(last_name))
    metaphone_match_last = int(jellyfish.metaphone(username) == jellyfish.metaphone(last_name))
    soundex_match_first = int(jellyfish.soundex(username) == jellyfish.soundex(first_name))
    metaphone_match_first = int(jellyfish.metaphone(username) == jellyfish.metaphone(first_name))
    
    
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)
    
    
    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +
        (metaphone_match_last * 10) +
        (soundex_match_first * 5) +  
        (metaphone_match_first * 5)+
        number_match_bonus
    )
    return min(composite, 100) 

def fetch_employees(csv_file_buffer):
    
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name'] 
    }

    try:
        
        df = pd.read_csv(csv_file_buffer)
        df.columns = df.columns.str.lower() 

        
        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    print(f"Renamed '{alias}' to '{canonical_name}'")
                    break 
                elif canonical_name in df.columns:
                    break 

        
        
        if 'employee_name' in df.columns and ('first_name' not in df.columns or 'last_name' not in df.columns):
            print("Detected 'employee_name' column. Attempting to split into 'first_name' and 'last_name'.")
            
            df['employee_name'] = df['employee_name'].astype(str).str.strip()

            
            name_parts = df['employee_name'].str.split(n=1, expand=True) 

            if len(name_parts.columns) > 0:
                df['first_name'] = name_parts[0].fillna('').str.strip()
                if len(name_parts.columns) > 1:
                    df['last_name'] = name_parts[1].fillna('').str.strip()
                else:
                    df['last_name'] = '' 
                print("Successfully split 'employee_name' into 'first_name' and 'last_name'.")
            else:
                df['first_name'] = ''
                df['last_name'] = ''
                print("Warning: Could not split 'employee_name' into 'first_name' and 'last_name'. They will be empty.")

        
        required_processing_columns = ['emp_id', 'first_name', 'last_name']
        if not all(col in df.columns for col in required_processing_columns):
            missing_cols = [col for col in required_processing_columns if col not in df.columns]
            flash(f"Error: Employee data CSV is missing required columns: {', '.join(missing_cols)}. Please ensure it has 'emp_id', 'first_name', 'last_name' or their aliases, or a 'full name' equivalent.", "error")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

       
        df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
        df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()

       
        df['employee_name'] = df['first_name'] + ' ' + df['last_name']
        
        df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()

        return df[['emp_id', 'employee_name', 'first_name', 'last_name']]

    except pd.errors.EmptyDataError:
        flash("Error: The uploaded Employee Data CSV file is empty.", "error")
        print("Error: The CSV file is empty.")
    except Exception as e:
        flash(f"An unexpected error occurred while processing the Employee Data CSV: {e}", "error")
        print(f"An unexpected error occurred: {e}")

    return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        employee_csv_file = request.files.get('employee_csv_file')
        usernames_csv_file = request.files.get('usernames_csv_file')

        
        if not employee_csv_file or employee_csv_file.filename == '':
            flash("Error: Please upload the Employee Data CSV.", "error")
            return redirect(url_for('index'))
        if not employee_csv_file.filename.lower().endswith('.csv'):
            flash("Error: Employee Data file must be a CSV.", "error")
            return redirect(url_for('index'))

        
        if not usernames_csv_file or usernames_csv_file.filename == '':
            flash("Error: Please upload the Usernames CSV for matching.", "error")
            return redirect(url_for('index'))
        if not usernames_csv_file.filename.lower().endswith('.csv'):
            flash("Error: Usernames file must be a CSV.", "error")
            return redirect(url_for('index'))

        
        employees_df = fetch_employees(employee_csv_file)
        if employees_df.empty:
            
            return redirect(url_for('index'))

        
        try:
            usernames_df = pd.read_csv(usernames_csv_file)
            usernames_df.columns = usernames_df.columns.str.lower() 
            if 'username' not in usernames_df.columns:
                flash("Error: The Usernames CSV must contain a column named 'username'.", "error")
                return redirect(url_for('index'))
            
           
            input_usernames = usernames_df['username'].astype(str).tolist()
        except pd.errors.EmptyDataError:
            flash("Error: The Usernames CSV file is empty.", "error")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Error reading Usernames CSV: {e}", "error")
            return redirect(url_for('index'))

        final_output_rows = [] 

        if employees_df.empty or not input_usernames:
            flash("No employee data or usernames to process. Please check your uploaded files.", "warning")
            return redirect(url_for('index'))

        
        for input_username in input_usernames:
            
            employees_df['current_score'] = employees_df.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'],
                    row['first_name'],
                    row['last_name'],
                    row['emp_id']
                ), axis=1
            )
            
            
            sorted_matches = employees_df.sort_values('current_score', ascending=False)
            
            
            relevant_matches = sorted_matches[sorted_matches['current_score'] > 0]

           
            top_match_found_for_username = False

        
            if not relevant_matches.empty:
                best_overall_match = relevant_matches.iloc[0]
                
                if best_overall_match['current_score'] >= TOP_MATCH_THRESHOLD:
                    
                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': best_overall_match['emp_id'],
                        'emp_name': best_overall_match['employee_name'],
                        'confidence_score': f"{best_overall_match['current_score']:.2f}%"
                    })
                    top_match_found_for_username = True
                    matches_for_others = relevant_matches[relevant_matches['emp_id'] != best_overall_match['emp_id']]
                else:
                    matches_for_others = relevant_matches
            else:
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': 'N/A',
                    'emp_name': 'N/A',
                    'confidence_score': '0.00%'
                })
                matches_for_others = pd.DataFrame() 
            if not top_match_found_for_username and not matches_for_others.empty:

                for rank_idx, (_, match_row) in enumerate(matches_for_others.head(NUM_OTHER_MATCHES + 1).iterrows()): 
                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': match_row['emp_id'],
                        'emp_name': match_row['employee_name'],
                        'confidence_score': f"{match_row['current_score']:.2f}%"
                    })
            elif top_match_found_for_username and not matches_for_others.empty:
                for rank_idx, (_, match_row) in enumerate(matches_for_others.head(NUM_OTHER_MATCHES).iterrows()):
                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': match_row['emp_id'],
                        'emp_name': match_row['employee_name'],
                        'confidence_score': f"{match_row['current_score']:.2f}%"
                    })
            
            
            if len(final_output_rows) > 0 and input_username == final_output_rows[-1]['username']:
                
                if final_output_rows[-1]['username'] != input_usernames[0] or len(input_usernames) > 1:
                     final_output_rows.append({
                        'username': '',
                        'emp_id': '',
                        'emp_name': '--- End of matches for this username ---', 
                        'confidence_score': ''
                    })

        if not final_output_rows:
            flash("No matches could be processed. Please check your CSV files and data.", "warning")
            return redirect(url_for('index'))

        results_df = pd.DataFrame(final_output_rows)

        results_df['temp_score'] = results_df['confidence_score'].str.replace('%', '')
        results_df['temp_score'] = pd.to_numeric(results_df['temp_score'], errors='coerce')
        results_df['temp_score'] = results_df['temp_score'].fillna(-1.0) 

        results_df['temp_username_sort'] = results_df['username'].apply(lambda x: x if x else '~') 

        results_df = results_df.sort_values(by=['temp_username_sort', 'temp_score'], ascending=[True, False])
        
        results_df = results_df.drop(columns=['temp_score', 'temp_username_sort'])

        output_buffer = io.StringIO()
        results_df.to_csv(output_buffer, index=False)
        output_buffer.seek(0) 
        flash("Match results CSV downloaded!", "success")
        return send_file(
            io.BytesIO(output_buffer.getvalue().encode('utf-8')), 
            mimetype='text/csv',
            as_attachment=True,
            download_name='username_matches_.csv' 
        )

    return render_template('index.html')

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)

