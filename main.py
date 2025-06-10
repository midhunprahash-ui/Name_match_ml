from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import io # Import io for in-memory file handling

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here' # Set a secret key for flash messages

# Define the UPLOAD_FOLDER for potential temporary file saving, though we process in-memory.
# For production, ensure this path is secure and writable.
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Max upload size: 16 MB

# Configure how many *additional* top matches to return besides the very best one
NUM_OTHER_MATCHES = 5 

def compute_match_score(username, full_name, first_name, last_name, emp_id):
    """
    Computes a composite match score between a username and employee details.
    Uses various string matching algorithms and applies bonuses.
    """
    # Convert all inputs to string and lowercase for consistent comparison
    username = str(username).lower()
    full_name = str(full_name).lower()
    first_name = str(first_name).lower()
    last_name = str(last_name).lower()
    emp_id = str(emp_id) # Convert emp_id to string for number matching

    # Bonus for matching numbers in username with employee ID
    numbers_in_username = re.findall(r'\d+', username)
    number_match_bonus = 0
    if numbers_in_username:
        if emp_id in numbers_in_username:
            number_match_bonus = 14 
    
    # Fuzzy string matching ratios for full name
    lev_full = fuzz.ratio(username, full_name)
    partial_full = fuzz.partial_ratio(username, full_name)
    token_set_full = fuzz.token_set_ratio(username, full_name)
    
    # Fuzzy string matching ratios for first name
    lev_first = fuzz.ratio(username, first_name)
    partial_first = fuzz.partial_ratio(username, first_name)
    token_set_first = fuzz.token_set_ratio(username, first_name)
    
    # Fuzzy string matching ratios for last name
    lev_last = fuzz.ratio(username, last_name)
    partial_last = fuzz.partial_ratio(username, last_name)
    token_set_last = fuzz.token_set_ratio(username, last_name)
    
    # Phonetic matching (Soundex and Metaphone)
    # Ensure inputs are not empty before applying phonetic algorithms
    soundex_match_last = 0
    if username and last_name: # Check if strings are not empty
        try:
            soundex_match_last = int(jellyfish.soundex(username) == jellyfish.soundex(last_name))
        except: # Handle potential errors if input is not suitable for soundex
            pass
    
    metaphone_match_last = 0
    if username and last_name:
        try:
            metaphone_match_last = int(jellyfish.metaphone(username) == jellyfish.metaphone(last_name))
        except:
            pass

    soundex_match_first = 0
    if username and first_name:
        try:
            soundex_match_first = int(jellyfish.soundex(username) == jellyfish.soundex(first_name))
        except:
            pass

    metaphone_match_first = 0
    if username and first_name:
        try:
            metaphone_match_first = int(jellyfish.metaphone(username) == jellyfish.metaphone(first_name))
        except:
            pass
    
    # Take maximum scores across full, first, and last names
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)
    
    # Calculate composite score
    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +
        (metaphone_match_last * 10) +
        (soundex_match_first * 10) +  
        (metaphone_match_first * 10) +
        number_match_bonus
    )
    return min(composite, 100) # Cap the score at 100

def fetch_employees(csv_file_buffer):
    """
    Fetches employee data from a CSV file-like object,
    standardizes column names, and handles combined name columns.
    
    Args:
        csv_file_buffer: A file-like object (e.g., from request.files['employee_csv_file'])
                         that pandas can read.
    Returns:
        A pandas DataFrame with standardized employee data, or an empty DataFrame
        if an error occurs.
    """
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name'] 
    }

    try:
        # Read the CSV directly from the buffer
        df = pd.read_csv(csv_file_buffer)
        df.columns = df.columns.str.lower() # Normalize incoming column names to lowercase

        # Attempt to rename columns to their canonical forms
        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    print(f"Renamed '{alias}' to '{canonical_name}'")
                    break # Move to the next canonical name once an alias is found and renamed
                elif canonical_name in df.columns:
                    break # Canonical name already present, no need to check aliases

        # Handle the 'employee_name' column being present instead of separate first_name/last_name
        # This takes precedence if first_name or last_name are missing but employee_name is present
        if 'employee_name' in df.columns and ('first_name' not in df.columns or 'last_name' not in df.columns):
            print("Detected 'employee_name' column. Attempting to split into 'first_name' and 'last_name'.")
            # Ensure 'employee_name' is string type to apply string operations
            df['employee_name'] = df['employee_name'].astype(str).str.strip()

            # Split 'employee_name' into 'first_name' and 'last_name'
            name_parts = df['employee_name'].str.split(n=1, expand=True) # Split only on the first space

            if len(name_parts.columns) > 0:
                df['first_name'] = name_parts[0].fillna('').str.strip()
                if len(name_parts.columns) > 1:
                    df['last_name'] = name_parts[1].fillna('').str.strip()
                else:
                    df['last_name'] = '' # Assign empty string if no last name part
                print("Successfully split 'employee_name' into 'first_name' and 'last_name'.")
            else:
                df['first_name'] = ''
                df['last_name'] = ''
                print("Warning: Could not split 'employee_name' into 'first_name' and 'last_name'. They will be empty.")

        # Verify that the *canonical* required columns are now present for processing
        required_processing_columns = ['emp_id', 'first_name', 'last_name']
        if not all(col in df.columns for col in required_processing_columns):
            missing_cols = [col for col in required_processing_columns if col not in df.columns]
            flash(f"Error: Employee data CSV is missing required columns: {', '.join(missing_cols)}. Please ensure it has 'emp_id', 'first_name', 'last_name' or their aliases, or a 'full name' equivalent.", "error")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

        # Ensure first_name and last_name are not null and are strings for concatenation
        df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
        df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()

        # Create or re-create 'employee_name' from first_name and last_name
        df['employee_name'] = df['first_name'] + ' ' + df['last_name']
        # Clean up any double spaces or leading/trailing spaces
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

        # Validate Employee Data CSV upload
        if not employee_csv_file or employee_csv_file.filename == '':
            flash("Error: Please upload the Employee Data CSV.", "error")
            return redirect(url_for('index'))
        if not employee_csv_file.filename.lower().endswith('.csv'):
            flash("Error: Employee Data file must be a CSV.", "error")
            return redirect(url_for('index'))

        # Validate Usernames CSV upload
        if not usernames_csv_file or usernames_csv_file.filename == '':
            flash("Error: Please upload the Usernames CSV for matching.", "error")
            return redirect(url_for('index'))
        if not usernames_csv_file.filename.lower().endswith('.csv'):
            flash("Error: Usernames file must be a CSV.", "error")
            return redirect(url_for('index'))

        # Process Employee Data CSV
        employees_df = fetch_employees(employee_csv_file)
        if employees_df.empty:
            # flash message already handled in fetch_employees if an error occurred
            return redirect(url_for('index'))

        # Process Usernames CSV
        try:
            usernames_df = pd.read_csv(usernames_csv_file)
            usernames_df.columns = usernames_df.columns.str.lower() # Normalize column names
            if 'username' not in usernames_df.columns:
                flash("Error: The Usernames CSV must contain a column named 'username'.", "error")
                return redirect(url_for('index'))
            
            # Convert username column to list of strings
            input_usernames = usernames_df['username'].astype(str).tolist()
        except pd.errors.EmptyDataError:
            flash("Error: The Usernames CSV file is empty.", "error")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Error reading Usernames CSV: {e}", "error")
            return redirect(url_for('index'))

        all_results_for_csv = [] # This will store the final rows for the output CSV

        if employees_df.empty or not input_usernames:
            flash("No employee data or usernames to process. Please check your uploaded files.", "warning")
            return redirect(url_for('index'))

        # Iterate through each username from the input CSV
        for input_username in input_usernames:
            # Apply the matching score to each employee for the current username
            employees_df['current_score'] = employees_df.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'],
                    row['first_name'],
                    row['last_name'],
                    row['emp_id']
                ), axis=1
            )
            
            # Sort all employees by their score for the current username
            sorted_matches = employees_df.sort_values('current_score', ascending=False)
            
            top_match_info = {
                'Input_Username': input_username,
                'Top_Match_Employee_ID': 'N/A',
                'Top_Match_Employee_Name': 'N/A',
                'Top_Match_Confidence_Score': '0.00%', # Added '%' here
                'Other_Matches_Details': ''
            }

            if not sorted_matches.empty:
                # Extract the very best match (Rank 1)
                best_match = sorted_matches.iloc[0]
                if best_match['current_score'] > 0: # Only consider it a match if score is positive
                    top_match_info['Top_Match_Employee_ID'] = best_match['emp_id']
                    top_match_info['Top_Match_Employee_Name'] = best_match['employee_name']
                    top_match_info['Top_Match_Confidence_Score'] = f"{best_match['current_score']:.2f}%" # Added '%' here
                
                # Collect details for the next NUM_OTHER_MATCHES (ranks 2 to NUM_OTHER_MATCHES + 1)
                other_matches_list = []
                # Slice from index 1 to get matches AFTER the top one
                # Limit to NUM_OTHER_MATCHES entries
                other_relevant_matches = sorted_matches.iloc[1 : NUM_OTHER_MATCHES + 1]

                for rank_idx, (_, match_row) in enumerate(other_relevant_matches.iterrows()):
                    if match_row['current_score'] > 0: # Only include if score is positive
                        other_matches_list.append(
                            f"Rank {rank_idx + 2}: {match_row['employee_name']} (ID: {match_row['emp_id']}, Score: {match_row['current_score']:.2f}%)" # Added '%' here
                        )
                
                # Join with newline character for multi-line cell in CSV
                top_match_info['Other_Matches_Details'] = "\n".join(other_matches_list)
            
            all_results_for_csv.append(top_match_info)

        if not all_results_for_csv:
            flash("No matches could be processed. Please check your CSV files and data.", "warning")
            return redirect(url_for('index'))

        # Convert the list of dictionaries to a DataFrame
        results_df = pd.DataFrame(all_results_for_csv)

        # Create an in-memory CSV file for download
        output_buffer = io.StringIO()
        results_df.to_csv(output_buffer, index=False)
        output_buffer.seek(0) # Rewind the buffer to the beginning

        # Send the CSV as a downloadable file
        flash("Match results CSV downloaded!", "success")
        return send_file(
            io.BytesIO(output_buffer.getvalue().encode('utf-8')), # Convert StringIO to BytesIO for send_file
            mimetype='text/csv',
            as_attachment=True,
            download_name='username_matches_detailed.csv' # New, more descriptive filename
        )

    # For GET request (initial page load)
    return render_template('index.html')

if __name__ == '__main__':
    # For development: create a temporary 'uploads' directory if it doesn't exist
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)

