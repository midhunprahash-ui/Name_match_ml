from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import io
import joblib # Import joblib to load the model
import numpy as np # For numerical operations, especially with thresholds

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

NUM_TOP_GROUP_MATCHES = 3
NUM_ADDITIONAL_POSSIBLE_MATCHES = 5
TOTAL_MATCHES_TO_DISPLAY = NUM_TOP_GROUP_MATCHES + NUM_ADDITIONAL_POSSIBLE_MATCHES
TOP_MATCH_THRESHOLD = 65

# Define a threshold for considering scores "similar" for ML tie-breaking
# If top scores are within this percentage point difference, ML is invoked.
SCORE_SIMILARITY_THRESHOLD = 2.0 # e.g., if scores are 88.4% and 87.5%, difference is 0.9%, within 2.0%

# --- ML Model Loading ---
ML_MODEL_PATH = 'fuzzy_match_model.joblib'
FEATURE_COLUMNS_PATH = 'feature_columns.joblib'
ml_model = None
feature_columns = None

try:
    ml_model = joblib.load(ML_MODEL_PATH)
    feature_columns = joblib.load(FEATURE_COLUMNS_PATH)
    print("ML model loaded successfully.")
except FileNotFoundError:
    print(f"Warning: ML model files ({ML_MODEL_PATH}, {FEATURE_COLUMNS_PATH}) not found.")
    print("Please run train_model.py first to train and save the model if you want ML tie-breaking.")
    ml_model = None # Ensure model is None if loading fails
except Exception as e:
    print(f"Error loading ML model: {e}")
    ml_model = None

# --- ORIGINAL FUZZY SCORE CALCULATION (renamed for clarity) ---
def compute_fuzzy_score(username, employee_name, first_name, last_name, emp_id):
    username_lower = str(username).lower()
    employee_name_lower = str(employee_name).lower()
    first_name_lower = str(first_name).lower()
    last_name_lower = str(last_name).lower()

    numbers_in_username = re.findall(r'\d+', username_lower)
    number_match_bonus = 0
    if numbers_in_username:
        if str(emp_id).lower() in numbers_in_username:
            number_match_bonus = 10

    lev_full = fuzz.ratio(username_lower, employee_name_lower)
    partial_full = fuzz.partial_ratio(username_lower, employee_name_lower)
    token_set_full = fuzz.token_set_ratio(username_lower, employee_name_lower)
    
    # Try to extract first and last name from username for more targeted comparison
    username_parts = re.split(r'[._\s]', username_lower)
    username_potential_first = ""
    username_potential_last = ""
    if len(username_parts) > 1:
        # Assuming common patterns like first.last or last.first
        username_potential_first = username_parts[-1] # For thakur.neha -> neha
        username_potential_last = username_parts[0]   # For thakur.neha -> thakur
    elif len(username_parts) == 1:
        # If no separator, just use the whole username string for first/last potential
        username_potential_first = username_parts[0]
        username_potential_last = username_parts[0]


    # Compare against parts of employee name
    # Prioritize comparison of username part to corresponding emp name part
    score_first_name_match = max(
        fuzz.ratio(username_potential_first, first_name_lower),
        fuzz.partial_ratio(username_potential_first, first_name_lower),
        fuzz.token_set_ratio(username_potential_first, first_name_lower)
    )
    score_last_name_match = max(
        fuzz.ratio(username_potential_last, last_name_lower),
        fuzz.partial_ratio(username_potential_last, last_name_lower),
        fuzz.token_set_ratio(username_potential_last, last_name_lower)
    )
    
    # Also consider if username parts match the *other* part of the employee name (e.g., if username is firstname.lastname, and employee name is lastname firstname)
    score_cross_first_name_match = max(
        fuzz.ratio(username_potential_first, last_name_lower),
        fuzz.partial_ratio(username_potential_first, last_name_lower),
        fuzz.token_set_ratio(username_potential_first, last_name_lower)
    )
    score_cross_last_name_match = max(
        fuzz.ratio(username_potential_last, first_name_lower),
        fuzz.partial_ratio(username_potential_last, first_name_lower),
        fuzz.token_set_ratio(username_potential_last, first_name_lower)
    )

    # Use a weighted average of direct and cross matches for parts
    avg_first_match = (score_first_name_match * 0.7 + score_cross_last_name_match * 0.3)
    avg_last_match = (score_last_name_match * 0.7 + score_cross_first_name_match * 0.3)


    # Maximize across the different types of fuzzy ratios for overall string comparison
    max_fuzz = max(lev_full, partial_full, token_set_full)

    # Additional phonetic checks
    soundex_match_last = int(jellyfish.soundex(last_name_lower) == jellyfish.soundex(username_potential_last))
    metaphone_match_last = int(jellyfish.metaphone(last_name_lower) == jellyfish.metaphone(username_potential_last))
    soundex_match_first = int(jellyfish.soundex(username_potential_first) == jellyfish.soundex(first_name_lower))
    metaphone_match_first = int(jellyfish.metaphone(username_potential_first) == jellyfish.metaphone(first_name_lower))
    
    # Increase the weighting for direct name part matches and phonetic matches
    composite = (
        (max_fuzz * 0.4) +           # Overall string similarity
        (avg_first_match * 0.2) +    # First name part match
        (avg_last_match * 0.2) +     # Last name part match
        (soundex_match_last * 8) +   # Strong bonus for last name phonetic match
        (metaphone_match_last * 8) + # Strong bonus for last name phonetic match
        (soundex_match_first * 4) +  # Moderate bonus for first name phonetic match
        (metaphone_match_first * 4) + # Moderate bonus for first name phonetic match
        number_match_bonus           # Bonus for ID match
    )
    
    return min(composite, 100) # Cap at 100

# --- FEATURE GENERATION FOR ML (same as before) ---
def generate_features(username, employee_name, first_name, last_name, emp_id):
    username_lower = str(username).lower().strip()
    employee_name_lower = str(employee_name).lower().strip()
    first_name_lower = str(first_name).lower().strip()
    last_name_lower = str(last_name).lower().strip()

    username_cleaned = re.sub(r'[^a-z0-9]', '', username_lower)
    username_no_dot = username_lower.replace('.', '')

    features = {}

    features['fuzz_ratio_full'] = fuzz.ratio(username_lower, employee_name_lower)
    features['fuzz_partial_full'] = fuzz.partial_ratio(username_lower, employee_name_lower)
    features['fuzz_token_sort_full'] = fuzz.token_sort_ratio(username_lower, employee_name_lower)
    features['fuzz_token_set_full'] = fuzz.token_set_ratio(username_lower, employee_name_lower)

    username_parts = re.split(r'[._\s]', username_lower)
    username_potential_first = ""
    username_potential_last = ""
    if len(username_parts) > 1:
        username_potential_first = username_parts[-1]
        username_potential_last = username_parts[0]
    elif len(username_parts) == 1:
        username_potential_first = username_parts[0]
        username_potential_last = username_parts[0]

    features['fuzz_ratio_username_first_to_emp_first'] = fuzz.ratio(username_potential_first, first_name_lower)
    features['fuzz_ratio_username_last_to_emp_last'] = fuzz.ratio(username_potential_last, last_name_lower)
    features['fuzz_ratio_username_first_to_emp_last'] = fuzz.ratio(username_potential_first, last_name_lower)
    features['fuzz_ratio_username_last_to_emp_first'] = fuzz.ratio(username_potential_last, first_name_lower)

    features['fuzz_ratio_cleaned_username_to_emp_name_no_space'] = fuzz.ratio(username_cleaned, employee_name_lower.replace(' ', ''))
    features['fuzz_token_set_cleaned_username_to_emp_name_no_space'] = fuzz.token_set_ratio(username_cleaned, employee_name_lower.replace(' ', ''))
    features['fuzz_ratio_no_dot_username_to_emp_name_no_space'] = fuzz.ratio(username_no_dot, employee_name_lower.replace(' ', ''))

    try:
        features['jelly_soundex_username_last'] = int(jellyfish.soundex(username_potential_last) == jellyfish.soundex(last_name_lower))
        features['jelly_metaphone_username_last'] = int(jellyfish.metaphone(username_potential_last) == jellyfish.metaphone(last_name_lower))
    except Exception:
        features['jelly_soundex_username_last'] = 0
        features['jelly_metaphone_username_last'] = 0

    try:
        features['jelly_soundex_username_first'] = int(jellyfish.soundex(username_potential_first) == jellyfish.soundex(first_name_lower))
        features['jelly_metaphone_username_first'] = int(jellyfish.metaphone(username_potential_first) == jellyfish.metaphone(first_name_lower))
    except Exception:
        features['jelly_soundex_username_first'] = 0
        features['jelly_metaphone_username_first'] = 0

    try:
        features['jelly_soundex_full'] = int(jellyfish.soundex(username_lower) == jellyfish.soundex(employee_name_lower))
        features['jelly_metaphone_full'] = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(employee_name_lower))
    except Exception:
        features['jelly_soundex_full'] = 0
        features['jelly_metaphone_full'] = 0

    features['exact_match_username_to_emp_name'] = int(username_lower == employee_name_lower)
    features['exact_match_username_no_dot_to_emp_name_no_space'] = int(username_no_dot == employee_name_lower.replace(' ', ''))
    features['exact_match_first_name_in_username'] = int(first_name_lower in username_lower or username_lower in first_name_lower)
    features['exact_match_last_name_in_username'] = int(last_name_lower in username_lower or username_lower in last_name_lower)

    numbers_in_username = re.findall(r'\d+', username_lower)
    features['id_match_bonus'] = int(str(emp_id).lower() in numbers_in_username)

    features['len_diff_username_emp_name'] = abs(len(username_lower) - len(employee_name_lower))
    features['len_ratio_username_emp_name'] = min(len(username_lower), len(employee_name_lower)) / (max(len(username_lower), len(employee_name_lower)) + 1e-6)

    return features

# --- ML REFINEMENT SCORE CALCULATION ---
def compute_ml_refinement_score(username, employee_name, first_name, last_name, emp_id):
    if ml_model is None or feature_columns is None:
        # If ML model isn't loaded, return a neutral score or the original score for this tie-breaking step
        return 0 # Or a fixed value to indicate it wasn't refined by ML
    
    features = generate_features(username, employee_name, first_name, last_name, emp_id)
    feature_values = [features.get(col, 0) for col in feature_columns]
    feature_df = pd.DataFrame([feature_values], columns=feature_columns)
    
    prediction_probability = ml_model.predict_proba(feature_df)[0][1] * 100
    return prediction_probability

# --- MODIFIED fetch_employees FUNCTION ---
def fetch_employees(file):
    # Core columns required for primary identification
    core_required_columns = ['first_name', 'last_name', 'emp_id']
    
    try:
        df = pd.read_csv(file)
        # Standardize column names (lowercase and replace spaces with underscores)
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        
        # Check for essential core columns first
        missing_core_columns = [col for col in core_required_columns if col not in df.columns]
        if missing_core_columns:
            flash(f"Error: Employee Data CSV is missing essential columns: {', '.join(missing_core_columns)}. "
                  "Please ensure it has 'first_name', 'last_name', and 'emp_id'.", "error")
            return pd.DataFrame()

        # Ensure 'first_name', 'last_name', and 'emp_id' are treated as strings and handle NaNs
        for col in ['first_name', 'last_name', 'emp_id']:
            df[col] = df[col].fillna('').astype(str)

        # Handle 'employee_name': Prefer existing, otherwise construct from first/last
        if 'employee_name' not in df.columns:
            print("Info: 'employee_name' column not found. Attempting to construct from 'first_name' and 'last_name'.")
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']
            df['employee_name'] = df['employee_name'].str.strip() # Remove leading/trailing spaces
            
            # Check if any 'employee_name' became empty after construction (e.g., if both first/last were empty)
            if (df['employee_name'] == '').any():
                flash("Warning: Some rows in Employee Data have empty 'employee_name' even after combining 'first_name' and 'last_name'. "
                      "This might lead to less accurate matches for those entries.", "warning")
        else:
            # If 'employee_name' exists, ensure it's a string and handle NaNs
            df['employee_name'] = df['employee_name'].fillna('').astype(str)


        return df
    except pd.errors.EmptyDataError:
        flash("Error: The Employee Data CSV file is empty.", "error")
        return pd.DataFrame()
    except pd.errors.ParserError:
        flash("Error: Could not parse Employee Data CSV. Please ensure it's a valid CSV format.", "error")
        return pd.DataFrame()
    except Exception as e:
        flash(f"Error reading Employee Data CSV: {e}", "error")
        return pd.DataFrame()


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
            # 1. Calculate initial fuzzy scores for all employees
            employees_df['fuzzy_score'] = employees_df.apply(
                lambda row: compute_fuzzy_score( # <<< USING ORIGINAL FUZZY SCORE
                    input_username,
                    row['employee_name'],
                    row['first_name'],
                    row['last_name'],
                    row['emp_id']
                ), axis=1
            )
            
            # Sort by fuzzy score initially
            sorted_by_fuzzy = employees_df.sort_values('fuzzy_score', ascending=False).copy()

            # Identify the top score
            if sorted_by_fuzzy.empty:
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': 'N/A',
                    'emp_name': 'N/A',
                    'confidence_score': '0.00%',
                    'match_type': 'No Match'
                })
                continue # Move to next username

            top_fuzzy_score = sorted_by_fuzzy.iloc[0]['fuzzy_score']

            # Find all employees with a score similar to the top score
            # These are the candidates for ML tie-breaking
            ambiguous_candidates = sorted_by_fuzzy[
                (top_fuzzy_score - sorted_by_fuzzy['fuzzy_score']) <= SCORE_SIMILARITY_THRESHOLD
            ].copy()

            # 2. Conditional ML Application:
            if ml_model and not ambiguous_candidates.empty and len(ambiguous_candidates) > 1:
                # Only apply ML if there's a model AND multiple similar scores
                print(f"Applying ML for tie-breaking for username: {input_username}")
                # Calculate ML refinement scores only for the ambiguous candidates
                ambiguous_candidates['ml_refinement_score'] = ambiguous_candidates.apply(
                    lambda row: compute_ml_refinement_score(
                        input_username,
                        row['employee_name'],
                        row['first_name'],
                        row['last_name'],
                        row['emp_id']
                    ), axis=1
                )
                
                # --- START OF FIX ---
                # Create a Series of ML scores from ambiguous candidates, indexed by emp_id
                ml_scores_series = ambiguous_candidates.set_index('emp_id')['ml_refinement_score']
                
                # Map these ML scores to the full employees_df using emp_id
                # .map() will automatically place NaN for emp_ids not in ml_scores_series.index
                ml_bonus_scores = employees_df['emp_id'].map(ml_scores_series) / 1000
                
                # Fill NaN values (for non-ambiguous candidates) with 0, so they don't affect fuzzy_score
                ml_bonus_scores = ml_bonus_scores.fillna(0)

                # Add this bonus to the fuzzy score to create the final sorting score
                employees_df['final_sort_score'] = employees_df['fuzzy_score'] + ml_bonus_scores
                # --- END OF FIX ---
                
                # Re-sort the entire DataFrame based on the refined scores
                sorted_matches = employees_df.sort_values('final_sort_score', ascending=False).copy()
                
            else:
                # If no ML model, or no tie-breaking needed, just use the fuzzy score
                sorted_matches = sorted_by_fuzzy
            
            # Now, proceed with selecting top matches based on the (potentially ML-influenced) sorted order
            matches_to_add = sorted_matches[sorted_matches['fuzzy_score'] > 0].head(TOTAL_MATCHES_TO_DISPLAY)
            # Use 'fuzzy_score' for confidence_score display, as ML is for tie-breaking order

            if matches_to_add.empty:
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': 'N/A',
                    'emp_name': 'N/A',
                    'confidence_score': '0.00%',
                    'match_type': 'No Match'
                })
                continue # Move to next username

            else:
                for rank_idx, (_, match_row) in enumerate(matches_to_add.iterrows()):
                    match_type = ''
                    if rank_idx == 0:
                        if match_row['fuzzy_score'] >= TOP_MATCH_THRESHOLD: # Use fuzzy score for threshold
                            match_type = 'Top Match'
                        else:
                            match_type = 'Best Match (Below Threshold)'
                    elif rank_idx < NUM_TOP_GROUP_MATCHES:
                        match_type = f'Top Match'
                    else:
                        match_type = f'Other Possible Match {rank_idx - NUM_TOP_GROUP_MATCHES + 1}'

                    final_output_rows.append({
                        'username': input_username,
                        'emp_id': match_row['emp_id'],
                        'emp_name': match_row['employee_name'],
                        'confidence_score': f"{match_row['fuzzy_score']:.2f}%", # Display fuzzy score as confidence
                        'match_type': match_type
                    })
            
            if i < len(input_usernames) - 1:
                final_output_rows.append({
                    'username': '',
                    'emp_id': '',
                    'emp_name': '', 
                    'confidence_score': '',
                    'match_type': '---' 
                })

        if not final_output_rows:
            flash("No matches could be processed. Please check your CSV files and data.", "warning")
            return redirect(url_for('index'))

        results_df = pd.DataFrame(final_output_rows)

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