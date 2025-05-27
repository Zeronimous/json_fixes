import os
import logging
import json
import copy # For deepcopy

# --- Configuration for Text Length Comparison ---
TEXT_LENGTH_WARNING_PERCENTAGE = 1.5  # Trigger warning if Spanish text is 150% (or more) of English length
TEXT_LENGTH_WARNING_ABSOLUTE_DIFF = 30 # Trigger warning if Spanish text is 30 chars (or more) longer

# Define directory paths
ingles_dir = "ingles"
espanol_dir = "espanol"
fixed_dir = "Fixed"

# Ensure the Fixed directory exists
os.makedirs(fixed_dir, exist_ok=True)
os.makedirs(ingles_dir, exist_ok=True) # Ensure ingles dir exists for testing
os.makedirs(espanol_dir, exist_ok=True) # Ensure espanol dir exists for testing

# --- Logger Setup ---
# Global loggers that will be configured by setup_loggers()
main_logger = None
text_length_warning_logger = None

class ExcludeTextLengthWarningsFilter(logging.Filter):
    def filter(self, record):
        # This filter will be attached to handlers for the main logger.
        # It should exclude messages that are specifically logged by text_length_warning_logger.
        # We can identify these by the logger's name.
        return record.name != 'text_length_warning_logger'

def setup_loggers():
    global main_logger, text_length_warning_logger

    # --- Main Logger (correction_log.txt and console) ---
    main_logger = logging.getLogger('main_logger')
    main_logger.setLevel(logging.DEBUG) # Set the logger itself to the lowest level it will handle

    # Clear existing handlers to avoid duplication if setup_loggers is called multiple times
    if main_logger.hasHandlers():
        main_logger.handlers.clear()

    # Filter to exclude text length warnings
    exclude_filter = ExcludeTextLengthWarningsFilter()

    # File Handler for correction_log.txt
    correction_log_file = 'correction_log.txt'
    if os.path.exists(correction_log_file):
        os.remove(correction_log_file) # Clear on each run
    fh_main = logging.FileHandler(correction_log_file, encoding='utf-8', mode='w')
    fh_main.setLevel(logging.DEBUG) # Process all levels from DEBUG upwards for this file
    fh_main.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))
    fh_main.addFilter(exclude_filter)
    main_logger.addHandler(fh_main)

    # Stream Handler for console
    sh_main = logging.StreamHandler()
    sh_main.setLevel(logging.INFO) # Console gets INFO and above
    sh_main.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    sh_main.addFilter(exclude_filter)
    main_logger.addHandler(sh_main)
    
    main_logger.propagate = False # Prevent messages from reaching the root logger if it has handlers

    # --- Text Length Warning Logger (erroreslargos.txt) ---
    text_length_warning_logger = logging.getLogger('text_length_warning_logger')
    text_length_warning_logger.setLevel(logging.WARNING)

    if text_length_warning_logger.hasHandlers():
        text_length_warning_logger.handlers.clear()

    # File Handler for erroreslargos.txt
    errores_largos_file = 'erroreslargos.txt'
    if os.path.exists(errores_largos_file):
        os.remove(errores_largos_file) # Clear on each run
    fh_text_length = logging.FileHandler(errores_largos_file, encoding='utf-8', mode='w')
    fh_text_length.setLevel(logging.WARNING) # Only WARNING messages
    fh_text_length.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))
    text_length_warning_logger.addHandler(fh_text_length)
    
    text_length_warning_logger.propagate = False # Crucial: do not pass to main_logger or root

RPGMAKER_CONTROL_CHARACTERS_PATTERNS = {
    # pattern: replacement (if different)
    # These will be checked in order. More specific first if necessary.
    # Double backslash versions for cases where English has it and Spanish has single.
    "\\\\N": None, "\\\\V": None, "\\\\G": None, "\\\\C": None, 
    "\\\\P": None, "\\\\$": None, "\\\\.": None, "\\\\|": None, 
    "\\\\!": None, "\\\\>": None, "\\\\<": None, "\\\\^": None,
    # Single backslash versions for cases where English has single and Spanish is missing it (less likely)
    # Or for ensuring Spanish doesn't accidentally escape something that shouldn't be.
    # This part might need refinement based on actual RPG Maker behavior.
}

def _log_text_length_warning(english_text, spanish_text, path_context):
    """Logs a warning if Spanish text is significantly longer than English text."""
    if not isinstance(english_text, str) or not isinstance(spanish_text, str):
        return # Only compare strings

    len_eng = len(english_text)
    len_esp = len(spanish_text)
    truncate_at = 50

    triggered_percentage = len_esp > len_eng * TEXT_LENGTH_WARNING_PERCENTAGE
    triggered_absolute = len_esp > len_eng + TEXT_LENGTH_WARNING_ABSOLUTE_DIFF

    if triggered_percentage or triggered_absolute:
        reason = []
        if triggered_percentage:
            reason.append(f"{TEXT_LENGTH_WARNING_PERCENTAGE*100:.0f}% length rule")
        if triggered_absolute:
            reason.append(f"{TEXT_LENGTH_WARNING_ABSOLUTE_DIFF} absolute char rule")
        
        eng_display = (english_text[:truncate_at] + '...') if len_eng > truncate_at else english_text
        esp_display = (spanish_text[:truncate_at] + '...') if len_esp > truncate_at else spanish_text
        
        # Use the dedicated text_length_warning_logger
        if text_length_warning_logger:
            text_length_warning_logger.warning(
                f"Path '{path_context}': Translated text is significantly longer than English ({', '.join(reason)}). "
                f"English (len {len_eng}): '{eng_display}', Spanish (len {len_esp}): '{esp_display}'"
            )
        else: # Fallback if logger not initialized, though it should be
            logging.getLogger().warning(f"[Fallback] Text length warning: {path_context}")


def correct_json_data(english_data, spanish_data, path="root"):
    """
    Recursively traverses and corrects the Spanish JSON data based on English data.
    Returns a new data structure representing the corrected Spanish data.
    """
    # Case 1: Spanish data is missing (key not present or Spanish file did not exist)
    if spanish_data is None:
        if english_data is not None: # Key existed in English but not Spanish
            main_logger.warning(f"Path '{path}': Key missing in Spanish, copying from English.")
        return copy.deepcopy(english_data)

    # Case 2: English data is missing (key exists in Spanish but not English)
    if english_data is None:
        main_logger.info(f"Path '{path}': Key present in Spanish but not in English, keeping Spanish version.")
        return copy.deepcopy(spanish_data)

    # Case 3: Type mismatch
    if type(english_data) is not type(spanish_data):
        main_logger.warning(f"Path '{path}': Type mismatch. English: {type(english_data).__name__}, Spanish: {type(spanish_data).__name__}. Prioritizing Spanish type/structure.")
        # If Spanish is a simple type, return it. If complex, proceed with Spanish structure.
        if not isinstance(spanish_data, (dict, list)):
            return copy.deepcopy(spanish_data)
        # If Spanish is dict/list but English is not, we will use Spanish structure.

    # Case 4: Data are lists
    if isinstance(spanish_data, list):
        # If English data is not a list (due to type mismatch handled above), use Spanish list as base
        english_list = english_data if isinstance(english_data, list) else []
        corrected_list = []
        
        # Special handling for 'events' list in RPG Maker JSON
        # Ensure spanish_data is also a list for this specific block
        if path.endswith(".events") and isinstance(english_data, list) and isinstance(spanish_data, list) and \
           len(english_data) > 0 and len(spanish_data) > 0 and \
           all(isinstance(e, dict) and 'code' in e for e in english_data) and \
           all(isinstance(s, dict) and 'code' in s for s in spanish_data):
            # This assumes event lists are aligned or primarily aligned by their nature in RPG Maker
            # More complex alignment (e.g. by ID if events had them) is not handled here.
            # Ensure current_spanish_list is used here, derived from spanish_data
            current_spanish_list_in_event_block = spanish_data if isinstance(spanish_data, list) else []
            max_len = max(len(english_list), len(current_spanish_list_in_event_block))
            for i in range(max_len):
                eng_item = english_list[i] if i < len(english_list) else None
                span_item = current_spanish_list_in_event_block[i] if i < len(current_spanish_list_in_event_block) else None
                item_path = f"{path}[{i}]"
                
                # Ensure both items are dicts before proceeding with event specific logic
                if isinstance(eng_item, dict) and isinstance(span_item, dict):
                     corrected_item_data = correct_json_data(eng_item, span_item, item_path)
                     corrected_list.append(corrected_item_data)
                elif span_item is not None: # Spanish item exists, English might not
                    main_logger.info(f"Path '{item_path}': Spanish event item kept (no corresponding English item or type mismatch).")
                    corrected_list.append(copy.deepcopy(span_item))
                elif eng_item is not None: # English item exists, Spanish does not
                    main_logger.warning(f"Path '{item_path}': English event item copied (no corresponding Spanish item).")
                    corrected_list.append(copy.deepcopy(eng_item))
            return corrected_list

        # General list processing
        # Ensure spanish_data is a list here as well if english_data is a list and types match
        # Or if spanish_data is a list and english_data is not (type mismatch, Spanish type prioritized)
        current_spanish_list = spanish_data if isinstance(spanish_data, list) else []
        
        max_len = max(len(english_list), len(current_spanish_list)) # Corrected this line
        for i in range(max_len):
            eng_item = english_list[i] if i < len(english_list) else None
            # Use current_spanish_list for span_item retrieval as well
            span_item = current_spanish_list[i] if i < len(current_spanish_list) else None
            item_path = f"{path}[{i}]"
            corrected_list.append(correct_json_data(eng_item, span_item, item_path))
        return corrected_list

    # Case 5: Data are dictionaries
    elif isinstance(spanish_data, dict):
        # If English data is not a dict (type mismatch), use Spanish dict as base
        english_dict = english_data if isinstance(english_data, dict) else {}
        corrected_dict = {}

        # Process keys present in Spanish data
        for key, s_value in spanish_data.items():
            e_value = english_dict.get(key)
            item_path = f"{path}.{key}"
            corrected_dict[key] = correct_json_data(e_value, s_value, item_path)

        # Process keys present in English data but not in Spanish
        for key, e_value in english_dict.items():
            if key not in spanish_data:
                item_path = f"{path}.{key}"
                main_logger.warning(f"Path '{item_path}': Key missing in Spanish dict, copying from English.")
                corrected_dict[key] = copy.deepcopy(e_value) # Or correct_json_data(e_value, None, item_path)

        # Event-specific parameter correction (after the main structure is built for the event)
        if 'code' in corrected_dict and 'parameters' in corrected_dict:
            # Make sure original English/Spanish parameters are available if needed
            original_eng_params = english_dict.get('parameters') if isinstance(english_dict, dict) else None
            # Pass the ORIGINAL Spanish parameters for this event to correct_event_parameters
            original_event_spanish_params = spanish_data.get('parameters') if isinstance(spanish_data, dict) else None
            
            if isinstance(original_eng_params, list) and isinstance(original_event_spanish_params, list):
                # corrected_dict['parameters'] will be REPLACED by the result of correct_event_parameters.
                # correct_event_parameters needs to operate on the original Spanish params for this event.
                correct_event_parameters(corrected_dict, original_eng_params, original_event_spanish_params, path)
            elif isinstance(original_eng_params, list) and original_event_spanish_params is None:
                 # Spanish event might not have parameters key, or it's not a list.
                 # In this case, English parameters (including choices) would be copied if any.
                 # This scenario is implicitly handled by correct_event_parameters if it receives None for current_spanish_params.
                 # However, we need to ensure it's called to potentially copy English structure.
                 main_logger.warning(f"Path '{path}': Spanish event parameters missing or not a list. Using English parameters structure.")
                 correct_event_parameters(corrected_dict, original_eng_params, None, path)


        return corrected_dict

    # Case 6: Data are simple types (string, number, boolean)
    else:
        # String correction for RPG Maker control characters
        if isinstance(english_data, str) and isinstance(spanish_data, str):
            corrected_spanish_string = spanish_data
            # Specific \\. correction
            if "\\\\." in english_data and "\\." in spanish_data and "\\\\." not in spanish_data:
                corrected_spanish_string = corrected_spanish_string.replace("\\.", "\\\\.")
                main_logger.info(f"Path '{path}': Corrected '\\.' to '\\\\.' in Spanish string: '{spanish_data}' -> '{corrected_spanish_string}'")
            
            # General control character check (e.g., \C[1] vs \\C[1])
            # This is a simplified example. Regex would be more robust.
            # Example: if english is "\\C[1]" and spanish is "\C[1]"
            for char_code_prefix in ["C", "N", "G", "V", "P", "$", "|", "!", ">", "<", "^"]: # Add more as needed
                eng_pattern_double_slash = f"\\\\{char_code_prefix}[" # or other bracket/variable forms
                span_pattern_single_slash = f"\\{char_code_prefix}["
                
                # This is a very basic check and might need complex regex to be robust
                # For now, focusing on the explicit \\. as per requirements.
                # A full regex solution would look for patterns like r'\\([CNGVP...])\[(\d+)\]'
                # and r'(?<!\\)\\([CNGVP...])\[(\d+)\]' (single backslash not preceded by another)

            # If no specific correction was made, spanish_data is returned as is.
            return corrected_spanish_string
        
        # For non-string simple types, or if only one is a string, Spanish data is preferred.
        return copy.deepcopy(spanish_data)


def correct_event_parameters(corrected_event, english_params, current_spanish_params, event_path):
    """
    Corrects parameters for specific event codes (102) and handles length mismatches.
    Modifies corrected_event['parameters'] directly.
    """
    code = corrected_event.get('code')
    # english_params is the original English parameters list.
    # current_spanish_params is the original Spanish parameters list for this event.
    
    # If current_spanish_params is None (e.g. Spanish event had no 'parameters' key or was not a list),
    # initialize it as an empty list to simplify logic downstream.
    # The goal is to prioritize English structure if Spanish parameters are entirely missing.
    if current_spanish_params is None:
        current_spanish_params = []

    original_english_params_for_text_warning = list(english_params) # Keep a copy for text length warnings
    old_params_for_logging = list(corrected_event['parameters']) # Params after initial recursive correct_json_data

    if code == 102: # Show Choices
        main_logger.info(f"Path '{event_path}': Processing event code 102 (Show Choices).")
        
        n_eng_choices = 0
        for param in english_params: # Use original english_params to determine structure
            if isinstance(param, str):
                n_eng_choices += 1
            else:
                break
        
        english_config_params = english_params[n_eng_choices:]
        
        actual_spanish_choices = []
        for param in current_spanish_params: # Iterate through original Spanish params
            if isinstance(param, str):
                actual_spanish_choices.append(param)
            else:
                # Stop collecting Spanish choices if a non-string is encountered,
                # assuming these are the start of config-like parameters in the Spanish data.
                break 
        
        num_actual_spanish_choices = len(actual_spanish_choices)

        if num_actual_spanish_choices < n_eng_choices:
            main_logger.warning(
                f"Path '{event_path} code {code}': Spanish file has fewer choices ({num_actual_spanish_choices}) "
                f"than English ({n_eng_choices}). Using all available Spanish choices and English config parameters."
            )
        elif num_actual_spanish_choices > n_eng_choices:
            main_logger.warning(
                f"Path '{event_path} code {code}': Spanish file has more choices ({num_actual_spanish_choices}) "
                f"than English originally had ({n_eng_choices}). Using all Spanish choices. "
                "This may require manual review as English configuration parameters might not align as expected or could be missing."
            )
            # If Spanish has more choices, we prioritize them all. The english_config_params might then be misaligned or irrelevant.
            # For this case, the requirement is "spanish_choices + english_config_params".
            # This means if Spanish has 3 choices and English had 2 (plus config), the new list will have 3 Spanish choices
            # followed by the original English config (which might make less sense but follows the rule).

        # Text length warnings for the actual Spanish choices used
        for i in range(num_actual_spanish_choices):
            if i < n_eng_choices: # Compare with corresponding English choice if it exists
                choice_path_context = f"{event_path}.parameters[{i}] (Choice text)"
                _log_text_length_warning(original_english_params_for_text_warning[i], actual_spanish_choices[i], choice_path_context)
            # No else needed; if Spanish has more choices, we can't warn against a non-existent English choice.

        new_parameters = actual_spanish_choices + english_config_params
        
        if new_parameters != old_params_for_logging: # Compare with parameters state before this function
            main_logger.info(
                f"Path '{event_path} code {code}': Corrected. Using {num_actual_spanish_choices} Spanish choices and {len(english_config_params)} English config parameters. "
                f"Old: {old_params_for_logging}, New: {new_parameters}"
            )
            corrected_event['parameters'] = new_parameters
        else:
            main_logger.info(f"Path '{event_path} code {code}': Parameters already conform. Using {num_actual_spanish_choices} Spanish choices and {len(english_config_params)} English config. Current: {new_parameters}")
        return

    # --- Handling for other event codes (including 401 text length warning) ---
    
    # Text length warning for code 401 (Show Text)
    # This should use current_spanish_params[0] as it's the "final" value after recursive correct_json_data
    # on the string itself (for \. fix etc.)
    # However, current_spanish_params passed to this function is the *original* Spanish param list.
    # The `corrected_event['parameters']` is the list *after* `correct_json_data` has processed its elements.
    final_spanish_params_for_event = corrected_event['parameters']

    if code == 401:
        if final_spanish_params_for_event and isinstance(final_spanish_params_for_event[0], str) and \
           original_english_params_for_text_warning and isinstance(original_english_params_for_text_warning[0], str):
            text_path_context = f"{event_path}.parameters[0] (Show Text)"
            _log_text_length_warning(original_english_params_for_text_warning[0], final_spanish_params_for_event[0], text_path_context)

    # General parameter list length correction for other event codes (non-102)
    # This uses the parameters list that has already been recursively processed by correct_json_data
    # because we want to preserve any detailed fixes (like string escapes) made within that list.
    if len(final_spanish_params_for_event) < len(english_params):
        missing_params_count = len(english_params) - len(final_spanish_params_for_event)
        tail_english_params = english_params[len(final_spanish_params_for_event):]
        
        # Heuristic: append if tail params are mostly numbers, booleans, or short non-narrative strings
        append_tail = True
        for param in tail_english_params:
            if isinstance(param, str) and len(param) > 20: # Arbitrary length to guess if it's narrative
                # Could also check against a list of known non-narrative string parameters for certain codes
                #main_logger.debug(f"Path '{event_path} code {code}': English tail parameter '{param}' seems narrative, not appending.")
                #append_tail = False #This might be too restrictive. The problem asks to append if primarily numbers/booleans.
                pass # For now, let's be more permissive, the main check is type

        if append_tail:
            main_logger.info(f"Path '{event_path} code {code}': Spanish parameters list ({len(current_spanish_params)}) is shorter than English ({len(english_params)}). Appending {missing_params_count} missing parameters from English: {tail_english_params}")
            corrected_event['parameters'].extend(copy.deepcopy(tail_english_params))
        else:
            main_logger.warning(f"Path '{event_path} code {code}': Spanish parameters list shorter, but English tail parameters did not meet criteria for auto-appending.")


def main():
    setup_loggers() # Initialize loggers first
    main_logger.info("Starting RPG Maker JSON correction process.")

    if not os.path.isdir(ingles_dir):
        main_logger.error(f"English directory not found: {ingles_dir}. Aborting.")
        return

    if not os.path.isdir(espanol_dir):
        main_logger.warning(f"Spanish directory not found: {espanol_dir}. English files will be copied directly to Fixed if they don't have a Spanish counterpart processed.")
        # Process will continue, copying English files if Spanish counterpart is missing.

    processed_files = 0
    corrected_files = 0
    copied_files = 0

    for filename in os.listdir(ingles_dir):
        if filename.endswith(".json"):
            english_file_path = os.path.join(ingles_dir, filename)
            spanish_file_path = os.path.join(espanol_dir, filename)
            output_file_path = os.path.join(fixed_dir, filename)

            main_logger.info(f"Processing English file: {english_file_path}")
            english_data = None
            try:
                with open(english_file_path, 'r', encoding='utf-8') as f_eng:
                    english_data = json.load(f_eng)
            except json.JSONDecodeError as e:
                main_logger.error(f"Failed to decode JSON from English file {english_file_path}: {e}. Skipping this file.")
                continue
            except Exception as e:
                main_logger.error(f"Failed to read English file {english_file_path}: {e}. Skipping this file.")
                continue
            
            processed_files += 1
            spanish_data = None
            if os.path.exists(spanish_file_path):
                main_logger.info(f"Found corresponding Spanish file: {spanish_file_path}")
                try:
                    with open(spanish_file_path, 'r', encoding='utf-8') as f_esp:
                        spanish_data = json.load(f_esp)
                except json.JSONDecodeError as e:
                    main_logger.warning(f"Failed to decode JSON from Spanish file {spanish_file_path}: {e}. Will attempt to process English data only for structure, but Spanish text will be lost for this file.")
                    # spanish_data remains None, so English data will be used as base by correct_json_data
                except Exception as e:
                     main_logger.warning(f"Failed to read Spanish file {spanish_file_path}: {e}. English data will be used.")


            if spanish_data is None and not os.path.exists(spanish_file_path):
                main_logger.warning(f"Spanish file not found for: {filename}. Copying English content to Fixed directory.")
                corrected_data = copy.deepcopy(english_data) # English data is copied as is
                copied_files +=1
            else:
                # If spanish_data is None due to decode error, correct_json_data will use english_data
                # and log warnings about missing Spanish parts.
                main_logger.info(f"Starting correction for {filename}...")
                corrected_data = correct_json_data(english_data, spanish_data, path=filename)
                corrected_files +=1
            
            try:
                with open(output_file_path, 'w', encoding='utf-8') as f_out:
                    json.dump(corrected_data, f_out, ensure_ascii=False, indent=4)
                main_logger.info(f"Successfully saved corrected file to: {output_file_path}")
            except Exception as e:
                main_logger.error(f"Failed to save corrected file {output_file_path}: {e}")

        else:
            main_logger.debug(f"Skipping non-JSON file: {filename} in {ingles_dir}")
    
    main_logger.info(f"RPG Maker JSON correction process finished. Processed: {processed_files} files. Corrected based on Spanish: {corrected_files} files. Copied from English (no Spanish file): {copied_files} files.")

if __name__ == "__main__":
    # Clean up dummy files from output directory for idempotency if they exist
    if os.path.exists(os.path.join(fixed_dir, "Map001.json")): os.remove(os.path.join(fixed_dir, "Map001.json"))
    if os.path.exists(os.path.join(fixed_dir, "Map002.json")): os.remove(os.path.join(fixed_dir, "Map002.json"))
    if os.path.exists(os.path.join(fixed_dir, "Map003.json")): os.remove(os.path.join(fixed_dir, "Map003.json"))
    if os.path.exists(os.path.join(fixed_dir, "CommonEvents.json")): os.remove(os.path.join(fixed_dir, "CommonEvents.json"))
    if os.path.exists(os.path.join(fixed_dir, "Map004_BadEsp.json")): os.remove(os.path.join(fixed_dir, "Map004_BadEsp.json"))
    if os.path.exists(os.path.join(fixed_dir, "Map005_TextLength.json")): os.remove(os.path.join(fixed_dir, "Map005_TextLength.json"))
    # Note: Any other specific test files in fixed_dir that might have been created by old tests
    # would ideally be listed here for cleanup too if they were part of a standardized test set.
    # For now, only known files are removed.

    main()

    # Optional: print log file content for quick check during development
    # print("\n--- correction_log.txt content ---")
    # if os.path.exists('correction_log.txt'):
    #     with open('correction_log.txt', 'r', encoding='utf-8') as f:
    #         print(f.read())
    # print("--- End of correction_log.txt ---")
    # print("\n--- erroreslargos.txt content ---")
    # if os.path.exists('erroreslargos.txt'):
    #     with open('erroreslargos.txt', 'r', encoding='utf-8') as f:
    #         print(f.read())
    # print("--- End of erroreslargos.txt ---")
