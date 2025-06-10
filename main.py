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


# Define the number of top group matches and additional possible matches
NUM_TOP_GROUP_MATCHES = 5
NUM_ADDITIONAL_POSSIBLE_MATCHES = 10
# The total number of matches to display for each username (5 + 10 = 15)
TOTAL_MATCHES_TO_DISPLAY = NUM_TOP_GROUP_MATCHES + NUM_ADDITIONAL_POSSIBLE_MATCHES

TOP_MATCH_THRESHOLD = 65

def compute_match_score(username, employee_name, first_name, last_name, emp_id):
    # Ensure all strings are treated consistently (e.g., lowercased) for robust matching
    username_lower = str(username).lower()
    employee_name_lower = str(employee_name).lower()
    first_name_lower = str(first_name).lower()
    last_name_lower = str(last_name).lower()

    numbers_in_username = re.findall(r'\d+', username_lower)
    number_match_bonus = 0
    if numbers_in_username:
        # Check if any number from username matches part of emp_id
        if str(emp_id).lower() in numbers_in_username: # Ensure emp_id is string and lower for consistent comparison
            number_match_bonus = 10 
    
    # Fuzzy string matching scores (0-100) using lowercased inputs
    lev_full = fuzz.ratio(username_lower, employee_name_lower)
    partial_full = fuzz.partial_ratio(username_lower, employee_name_lower)
    token_set_full = fuzz.token_set_ratio(username_lower, employee_name_lower)
    
    lev_first = fuzz.ratio(username_lower, first_name_lower)
    partial_first = fuzz.partial_ratio(username_lower, first_name_lower)
    token_set_first = fuzz.token_set_ratio(username_lower, first_name_lower)
    
    lev_last = fuzz.ratio(username_lower, last_name_lower)
    partial_last = fuzz.partial_ratio(username_lower, last_name_lower)
    token_set_last = fuzz.token_set_ratio(username_lower, last_name_lower) 
    
    # Phonetic matching (0 or 1, then scaled) using lowercased inputs
    soundex_match_last = int(jellyfish.soundex(username_lower) == jellyfish.soundex(last_name_lower))
    metaphone_match_last = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(last_name_lower))
    soundex_match_first = int(jellyfish.soundex(username_lower) == jellyfish.soundex(first_name_lower))
    metaphone_match_first = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(first_name_lower))
    
    # Take the maximum of different string comparisons for each fuzzy type
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last) 
    
    # Composite score calculation with original weights and bonuses
    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +  
        (metaphone_match_last * 10) +
        (soundex_match_first * 5) +  
        (metaphone_match_first * 5) + 
        number_match_bonus
    )
    return min(composite, 100) # Cap the score at 100

def fetch_employees(csv_file_buffer):
    
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name'] 
    }

    try:
        # Read the CSV from the buffer
        df = pd.read_csv(csv_file_buffer)
        df.columns = df.columns.str.lower() 

        # Rename columns to canonical names
        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    break 
                elif canonical_name in df.columns:
                    break 

        # Handle employee_name, first_name, last_name consistency
        # Ensure employee_name is created if not present or combine first/last if they are.
        # Prioritize existing employee_name if it's the only one, then split.
        # Otherwise, construct employee_name from first_name and last_name.

        if 'employee_name' not in df.columns and ('first_name' in df.columns or 'last_name' in df.columns):
            df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
            df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']
            df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()
        elif 'employee_name' in df.columns:
            df['employee_name'] = df['employee_name'].astype(str).str.strip()
            if 'first_name' not in df.columns and 'last_name' not in df.columns:
                name_parts = df['employee_name'].str.split(n=1, expand=True) 
                df['first_name'] = name_parts[0].fillna('').str.strip()
                if len(name_parts.columns) > 1:
                    df['last_name'] = name_parts[1].fillna('').str.strip()
                else:
                    df['last_name'] = ''
            elif 'first_name' in df.columns and 'last_name' in df.columns:

                df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
                df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
                df['employee_name'] = df['first_name'] + ' ' + df['last_name']
                df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()


        # Ensure required columns are present after all processing
        required_processing_columns = ['emp_id', 'first_name', 'last_name', 'employee_name'] 
        if not all(col in df.columns for col in required_processing_columns):
            missing_cols = [col for col in required_processing_columns if col not in df.columns]
            flash(f"Error: Employee data CSV is missing required columns: {', '.join(missing_cols)}. Please ensure it has 'emp_id', 'first_name', 'last_name' or their aliases, or a 'full name' equivalent.", "error")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

        # Final cleaning and type conversion for consistency
        df['emp_id'] = df['emp_id'].astype(str).str.strip() 
        df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
        df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
        df['employee_name'] = df['employee_name'].fillna('').astype(str).str.strip()


        return df[['emp_id', 'employee_name', 'first_name', 'last_name']]

    except pd.errors.EmptyDataError:
        flash("Error: The uploaded Employee Data CSV file is empty.", "error")
        print("Error: The CSV file is empty.")
    except Exception as e:
        flash(f"An unexpected error occurred while processing the Employee Data CSV: {e}", "error")
        print(f"An unexpected error occurred while processing employee data: {e}")

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

        for i, input_username in enumerate(input_usernames):
            # Compute scores for the current username against all employees
            employees_df['current_score'] = employees_df.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'],
                    row['first_name'],
                    row['last_name'],
                    row['emp_id']
                ), axis=1
            )
            
            # Sort matches by score in descending order
            sorted_matches = employees_df.sort_values('current_score', ascending=False).copy() 
            
            # Get up to TOTAL_MATCHES_TO_DISPLAY (15) relevant matches (score > 0)
            matches_to_add = sorted_matches[sorted_matches['current_score'] > 0].head(TOTAL_MATCHES_TO_DISPLAY)

            if matches_to_add.empty:
                # No matches found for this username with score > 0
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': 'N/A',
                    'emp_name': 'N/A',
                    'confidence_score': '0.00%',
                    'match_type': 'No Match'
                })
            else:
                for rank_idx, (_, match_row) in enumerate(matches_to_add.iterrows()):
                    match_type = ''
                    if rank_idx == 0:
                        # The very best match
                        if match_row['current_score'] >= TOP_MATCH_THRESHOLD:
                            match_type = 'Top Match'
                        else:
                            match_type = 'Best Match (Below Threshold)'
                    elif rank_idx < NUM_TOP_GROUP_MATCHES:
                        # The remaining matches within the "top 5" group
                        match_type = 'Top Match'
                    else:
                        # The matches within the "other 10 possible matches" group
                        match_type = f'Possible Match {rank_idx - NUM_TOP_GROUP_MATCHES + 1}'

                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': match_row['emp_id'],
                        'emp_name': match_row['employee_name'],
                        'confidence_score': f"{match_row['current_score']:.2f}%",
                        'match_type': match_type
                    })
            
            # Add a separator row between usernames for better readability in the CSV
            # Only add if it's not the last username
            if i < len(input_usernames) - 1:
                final_output_rows.append({
                    'username': '',
                    'emp_id': '',
                    'emp_name': '', 
                    'confidence_score': '',
                    'match_type': '---' # Separator indicator
                })

        if not final_output_rows:
            flash("No matches could be processed. Please check your CSV files and data.", "warning")
            return redirect(url_for('index'))

        results_df = pd.DataFrame(final_output_rows)

        # The DataFrame is already ordered correctly by username and then by score within each username,
        # with separators added sequentially.

        output_buffer = io.StringIO()
        results_df.to_csv(output_buffer, index=False)
        output_buffer.seek(0) 
        flash("Match results CSV downloaded!", "success")
        return send_file(
            io.BytesIO(output_buffer.getvalue().encode('utf-8')), 
            mimetype='text/csv',
            as_attachment=True,
            download_name='username_matches.csv' 
        )

    return render_template('index.html')

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)