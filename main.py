from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import io

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Max upload size: 16 MB

# Constants for match display and thresholds
NUM_TOP_GROUP_MATCHES = 4
NUM_ADDITIONAL_POSSIBLE_MATCHES = 2
TOTAL_MATCHES_TO_DISPLAY = NUM_TOP_GROUP_MATCHES + NUM_ADDITIONAL_POSSIBLE_MATCHES
TOP_MATCH_THRESHOLD = 75


def compute_match_score(username, employee_name, first_name, last_name, emp_id):
    """
    Computes a comprehensive match score between a given username and an
    employee's details. This function returns 100.0 for exact pattern matches
    and a composite fuzzy score otherwise. The logic within this function
    remains unchanged as per the user's request.

    Args:
        username (str): The username string to match.
        employee_name (str): The full employee name.
        first_name (str): The employee's first name.
        last_name (str): The employee's last name.
        emp_id (str): The employee's ID.

    Returns:
        float: A calculated confidence score, capped at 100.0.
    """
    # Normalize inputs to lowercase and strip whitespace
    username_lower = str(username).lower().strip()
    employee_name_lower = str(employee_name).lower().strip()
    first_name_lower = str(first_name).lower().strip()
    last_name_lower = str(last_name).lower().strip()

    # --- Exact Pattern Matches (return 100.0 immediately) ---
    # These conditions are kept as they were in the original request.
    # The adjustment for multiple 100% matches will happen in the index() route.
    if first_name_lower and last_name_lower:
        if username_lower == f"{first_name_lower}.{last_name_lower}": return 100.0
        if username_lower == f"{last_name_lower}.{first_name_lower}": return 100.0
        if len(first_name_lower) > 0 and username_lower == f"{first_name_lower[0]}.{last_name_lower}": return 100.0
        if len(last_name_lower) > 0 and username_lower == f"{first_name_lower}.{last_name_lower[0]}": return 100.0
        if username_lower == f"{first_name_lower}{last_name_lower}": return 100.0
        if username_lower == f"{last_name_lower}{first_name_lower}": return 100.0
        if username_lower == f"{first_name_lower} {last_name_lower}": return 100.0
        if username_lower == f"{last_name_lower} {first_name_lower}": return 100.0
        if username_lower == f"{first_name_lower}.{last_name_lower[:2]}": return 100.0
        if username_lower == f"{last_name_lower}.{first_name_lower[:2]}": return 100.0
        if username_lower == f"{first_name_lower}{last_name_lower[:2]}": return 100.0

    # --- Fuzzy and Phonetic Matching (if no exact pattern match) ---
    # Bonuses based on Employee ID
    numbers_in_username = re.findall(r'\d+', username_lower)
    number_match_bonus = 0
    if numbers_in_username:
        if str(emp_id).lower() in numbers_in_username:
            number_match_bonus = 20

    # Fuzzy String Matching (using thefuzz library)
    lev_full = fuzz.ratio(username_lower, employee_name_lower)
    partial_full = fuzz.partial_ratio(username_lower, employee_name_lower)
    token_set_full = fuzz.token_set_ratio(username_lower, employee_name_lower)

    lev_first = fuzz.ratio(username_lower, first_name_lower)
    partial_first = fuzz.partial_ratio(username_lower, first_name_lower)
    token_set_first = fuzz.token_set_ratio(username_lower, first_name_lower)

    lev_last = fuzz.ratio(username_lower, last_name_lower)
    partial_last = fuzz.partial_ratio(username_lower, last_name_lower)
    token_set_last = fuzz.token_set_ratio(username_lower, last_name_lower)

    # Phonetic Matching (using jellyfish library)
    soundex_match_last = int(jellyfish.soundex(username_lower) == jellyfish.soundex(last_name_lower))
    metaphone_match_last = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(last_name_lower))
    soundex_match_first = int(jellyfish.soundex(username_lower) == jellyfish.soundex(first_name_lower))
    metaphone_match_first = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(first_name_lower))

    # Initial Character Matching Bonus
    initial_match_bonus = 0
    if first_name_lower and username_lower:
        if username_lower[0] == first_name_lower[0]:
            initial_match_bonus += 5
        if '.' in username_lower:
            parts = username_lower.split('.')
            if len(parts) > 1 and parts[1] and first_name_lower:
                if parts[1][0] == first_name_lower[0]:
                    initial_match_bonus += 5

    # Direct Substring Inclusion Bonus
    direct_first_name_substring_bonus = 0
    if first_name_lower and first_name_lower in username_lower:
        direct_first_name_substring_bonus = 10

    direct_last_name_substring_bonus = 0
    if last_name_lower and last_name_lower in username_lower:
        direct_last_name_substring_bonus = 10

    # Calculate Composite Score
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)

    composite = (
        (max_lev * 0.3) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 5) +
        (metaphone_match_last * 5) +
        (soundex_match_first * 2) +
        (metaphone_match_first * 2) +
        number_match_bonus +
        initial_match_bonus +
        direct_first_name_substring_bonus +
        direct_last_name_substring_bonus
    )
    return min(composite, 100) # Cap the score at 100.0


def fetch_employees(csv_file_buffer):
    """
    Reads employee data from a CSV file, standardizes column names, and performs
    basic data cleaning and preparation.

    Args:
        csv_file_buffer: A file-like object containing the CSV data.

    Returns:
        pd.DataFrame: A DataFrame with standardized employee data, or an empty DataFrame
                      if an error occurs or required columns are missing.
    """
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name']
    }

    try:
        df = pd.read_csv(csv_file_buffer)
        df.columns = df.columns.str.lower() # Convert all column names to lowercase

        # Rename columns to canonical names if aliases are found
        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    break
                elif canonical_name in df.columns:
                    break

        # Generate 'employee_name', 'first_name', 'last_name' if missing
        if 'employee_name' not in df.columns and ('first_name' in df.columns or 'last_name' in df.columns):
            df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
            df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']
            df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()
        elif 'employee_name' in df.columns:
            df['employee_name'] = df['employee_name'].astype(str).str.strip()
            if 'first_name' not in df.columns and 'last_name' not in df.columns:
                # Attempt to split employee_name into first and last if they don't exist
                name_parts = df['employee_name'].str.split(n=1, expand=True)
                df['first_name'] = name_parts[0].fillna('').str.strip()
                if len(name_parts.columns) > 1:
                    df['last_name'] = name_parts[1].fillna('').str.strip()
                else:
                    df['last_name'] = '' # Assign empty string if only one part
            elif 'first_name' in df.columns and 'last_name' in df.columns:
                # If both exist, just ensure they're clean and reconstruct employee_name
                df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
                df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
                df['employee_name'] = df['first_name'] + ' ' + df['last_name']
                df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()


        # Validate presence of essential columns after processing
        required_processing_columns = ['emp_id', 'first_name', 'last_name', 'employee_name']
        if not all(col in df.columns for col in required_processing_columns):
            missing_cols = [col for col in required_processing_columns if col not in df.columns]
            flash(f"Error: Employee data CSV is missing required columns: {', '.join(missing_cols)}. Please ensure it has 'emp_id', 'first_name', 'last_name' or their aliases, or a 'full name' equivalent.", "error")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

        # Final cleaning for relevant columns
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
    """
    Handles the main logic for uploading CSVs, processing username matches,
    and downloading results.
    """
    if request.method == 'POST':
        employee_csv_file = request.files.get('employee_csv_file')
        usernames_csv_file = request.files.get('usernames_csv_file')

        # --- Input File Validation ---
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
        if employees_df.empty: # If fetch_employees returned an empty DataFrame due to errors
            return redirect(url_for('index'))

        # --- Process Usernames CSV ---
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

        final_output_rows = [] # List to store all rows for the final output CSV

        if employees_df.empty or not input_usernames:
            flash("No employee data or usernames to process. Please check your uploaded files.", "warning")
            return redirect(url_for('index'))

        # --- Main Matching Loop ---
        for i, input_username in enumerate(input_usernames):
            # Compute scores for all employees against the current input_username
            employees_df['current_score'] = employees_df.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'],
                    row['first_name'],
                    row['last_name'],
                    row['emp_id']
                ), axis=1
            )

            # Identify all employees that received an initial 100% score (exact pattern match)
            exact_matches_100_percent = employees_df[employees_df['current_score'] == 100.0].copy()
            exact_match_count = len(exact_matches_100_percent)

            # Determine the score to apply for exact matches based on their count
            if exact_match_count == 1:
                # If only one employee has an exact pattern match, it stays 100%
                exact_score_to_apply = 100.0
            elif exact_match_count > 1:
                # If multiple employees have an exact pattern match, reduce to 95%
                exact_score_to_apply = 95.0
            else:
                # No exact pattern matches, so no special adjustment for 100%/95%
                exact_score_to_apply = 0.0 # This value is not actually used for non-exact matches


            # Apply the adjusted score to the identified exact matches
            if exact_match_count > 0:
                # Update the 'current_score' for those specific employees found to be exact matches
                # This ensures that if there are multiple "John Does", all of them get 95% if they matched exactly.
                employees_df.loc[employees_df['current_score'] == 100.0, 'current_score'] = exact_score_to_apply


            # Sort all employees by their potentially adjusted 'current_score' in descending order.
            sorted_matches = employees_df.sort_values('current_score', ascending=False).copy()

            # Filter for matches that have a score greater than 0, and take the top N matches for display.
            matches_to_add = sorted_matches[sorted_matches['current_score'] > 0].head(TOTAL_MATCHES_TO_DISPLAY)

            # --- Append Results to Output List ---
            if matches_to_add.empty:
                # If no matches are found, add a 'No Match' row.
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': 'N/A',
                    'emp_name': 'N/A',
                    'confidence_score': '0.00%',
                    'match_type': 'No Match'
                })
            else:
                # Add each identified match to the output list with appropriate match_type
                for rank_idx, (_, match_row) in enumerate(matches_to_add.iterrows()):
                    score_value = match_row['current_score']
                    match_type = ''

                    # Assign specific match types based on the score and rank
                    if score_value == 100.0:
                        match_type = 'Exact Single Match'
                    elif score_value == 95.0:
                        match_type = 'Exact Multiple Match'
                    elif rank_idx == 0:
                        # For the highest scoring non-exact match (fuzzy, etc.)
                        if score_value >= TOP_MATCH_THRESHOLD:
                            match_type = 'Top Match'
                        else:
                            match_type = 'Best Match'
                    elif rank_idx < NUM_TOP_GROUP_MATCHES:
                        # Other top group matches based on fuzzy score
                        match_type = 'Top Match'
                    else:
                        # Remaining possible matches (below the top group)
                        match_type = 'Other Possible Match'

                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': match_row['emp_id'],
                        'emp_name': match_row['employee_name'],
                        'confidence_score': f"{score_value:.2f}%",
                        'match_type': match_type
                    })

            # Add a separator row between different input usernames for clarity in the output CSV
            if i < len(input_usernames) - 1:
                final_output_rows.append({
                    'username': '',
                    'emp_id': '',
                    'emp_name': '',
                    'confidence_score': '',
                    'match_type': '---'
                })

        # --- Final Output Generation ---
        if not final_output_rows:
            flash("No matches could be processed. Please check your CSV files and data.", "warning")
            return redirect(url_for('index'))

        # Convert the list of dictionaries into a Pandas DataFrame
        results_df = pd.DataFrame(final_output_rows)

        # Prepare the DataFrame to be sent as a CSV file
        output_buffer = io.StringIO()
        results_df.to_csv(output_buffer, index=False) # Write DataFrame to the buffer as CSV
        output_buffer.seek(0) # Reset buffer's position to the beginning

        flash("Match results CSV downloaded!", "success")
        return send_file(
            io.BytesIO(output_buffer.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='username_matches.csv'
        )

    # Render the upload form if it's a GET request
    return render_template('index.html')

if __name__ == '__main__':
    # Ensure 'uploads' directory exists
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    # Create a dummy index.html for testing if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f:
            f.write
    app.run(debug=True)
