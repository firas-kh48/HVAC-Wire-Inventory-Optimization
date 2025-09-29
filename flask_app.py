from flask import Flask, render_template, request, redirect, url_for
import os
import json

app = Flask(__name__)

# Add escapejs filter
def escapejs_filter(s):
    if s is None:
        return ''
    # Convert to string in case it's not already
    s = str(s)
    # Escape special characters
    s = s.replace('\\', '\\\\').replace('\'', '\\\'').replace('"', '\\"').replace('\n', '\\n')
    return s

app.jinja_env.filters['escapejs'] = escapejs_filter

# Helper functions
def generate_reference(wire_type, length):
    # Abbreviation for Red Cable
    if wire_type == 'Red Cable':
        return "R"

    # Abbreviation for Earth (any type starting with 'Earth')
    if wire_type.startswith('Earth'):
        parts = wire_type.split()
        if len(parts) == 2:  # e.g. 'Earth 14'
            return f"ER {parts[1]} - {length}"
        else:
            return f"ER - {length}"

    # Map wire type to prefix for other cable types
    type_prefix = {
        'Shielded': 'SH',
        'Armored': 'AR',
        'Earth Green': 'EG',
        'Earth Yellow': 'EY'
    }

    # Find the matching type prefix
    for wire_type_name, prefix in type_prefix.items():
        if wire_type.startswith(wire_type_name):
            # For Shielded cables, include "Core" in the reference
            if wire_type_name == 'Shielded':
                # Extract the size (e.g., '6' from 'Shielded 6')
                size = wire_type[len(wire_type_name):].strip()
                return f"{prefix} {size} Core - {length}"
            else:
                # For other cable types, use the original format
                size = wire_type[len(wire_type_name):].strip()
                return f"{prefix} {size} - {length}"

    # Fallback to original format if no match found, but add spaces around hyphen
    import re
    match = re.match(r"([A-Za-z ]+)(\d+(?:/\d+)?|\(\d+/\d+\))", wire_type)
    if match:
        name, size = match.groups()
        return f"{name.strip()} {size} - {length}"
    return f"{wire_type} - {length}"

def read_inventory():
    try:
        with open('inventory.txt', 'r') as file:
            inventory = {}
            for line in file:
                parts = line.strip().split(',')
                if len(parts) == 2:  # Old format: name,qty
                    name, qty = parts
                    wire_type, length_str = name.split('_')
                    try:
                        length = float(length_str)
                        ref = generate_reference(wire_type, length)
                        inventory[ref] = {
                            'type': wire_type,
                            'length': length,
                            'quantity': int(qty),
                            'reference': ref
                        }
                    except (ValueError, TypeError):
                        # Skip invalid entries
                        continue
                elif len(parts) == 4:  # New format: type,length,qty,ref
                    wire_type, length, qty, ref = parts
                    # Convert length to float first, then round to 1 decimal place
                    length_float = round(float(length), 1)
                    inventory[ref] = {
                        'type': wire_type,
                        'length': length_float,
                        'quantity': int(qty),
                        'reference': ref
                    }
            return inventory
    except FileNotFoundError:
        return {}

def write_inventory(inventory):
    with open('inventory.txt', 'w') as file:
        for ref, data in inventory.items():
            file.write(f"{data['type']},{data['length']},{data['quantity']},{data['reference']}\n")

@app.route('/', methods=['GET', 'POST'])
def index():
    inventory = read_inventory()
    message = ""
    search_results = None
    edit_ref = None

    # Cable categories and their sizes
    cable_categories = {
        'Shielded': ['6', '4', '3', '2'],
        'Armored': ['14', '12', '10', '8', '6', '4', '2', '1', '(1/0)', '(2/0)'],
        'Earth': ['14', '12', '10', '8', '6', '4', '2', '1', '(1/0)', '(2/0)'],
        'Red Cable': ['14', '12', '10', '8', '6', '4', '2', '1', '(1/0)', '(2/0)']
    }

    # For backward compatibility
    wire_types = []
    for category, sizes in cable_categories.items():
        for size in sizes:
            wire_types.append(f"{category} {size}")

    lengths = list(range(2, 21))  # 2-20 meters

    if request.method == 'POST':
        wire_type = request.form.get('wire_type')
        length = request.form.get('length')
        action = request.form.get('action')

        if action == 'add' and wire_type and length:
            try:
                # Convert length to float and round to 1 decimal place
                length_float = round(float(length), 1)
                ref = generate_reference(wire_type, length_float)
                if ref in inventory:
                    inventory[ref]['quantity'] += 1
                else:
                    inventory[ref] = {
                        'type': wire_type,
                        'length': length_float,
                        'quantity': 1,
                        'reference': ref
                    }
                write_inventory(inventory)
                message = f"Wire added to inventory with reference: {ref}"
            except (ValueError, TypeError):
                message = "Please enter a valid length"

        elif action == 'remove' and wire_type and length:
            try:
                length_float = round(float(length), 1)
                ref = generate_reference(wire_type, length_float)
                if ref in inventory:
                    if inventory[ref]['quantity'] > 1:
                        inventory[ref]['quantity'] -= 1
                        message = f"Removed 1 piece of {wire_type} ({length_float}m) from inventory"
                    else:
                        del inventory[ref]
                        message = f"Removed {wire_type} ({length_float}m) from inventory"
                    write_inventory(inventory)
                else:
                    message = f"No {wire_type} ({length_float}m) found in inventory"
            except (ValueError, TypeError):
                message = "Please enter a valid length"

        # Handle update quantity action from the edit modal
        elif action == 'update_quantity':
            ref = request.form.get('reference')
            try:
                quantity = int(request.form.get('quantity', 0))
                if ref in inventory and quantity > 0:
                    inventory[ref]['quantity'] = quantity
                    write_inventory(inventory)
                    message = f"Updated quantity to {quantity} for {inventory[ref]['type']} ({inventory[ref]['length']}m)"
                else:
                    message = "Invalid reference or quantity"
            except (ValueError, TypeError):
                message = "Please enter a valid quantity"

        elif action == 'search':
            search_results = {}
            try:
                if wire_type and length:
                    # If both wire type and length are provided, search for exact match
                    length_float = round(float(length), 1)
                    ref = generate_reference(wire_type, length_float)
                    if ref in inventory:
                        search_results[ref] = inventory[ref]
                elif wire_type:
                    # If only wire type is provided, show all lengths of that wire type
                    for ref, data in inventory.items():
                        if data['type'] == wire_type:
                            search_results[ref] = data
                    if not search_results:
                        message = f"No inventory found for {wire_type}"
                else:
                    # If no wire type is provided, show all inventory
                    search_results = inventory.copy()
                    if not search_results:
                        message = "No inventory found"
            except (ValueError, TypeError):
                # If length is invalid but wire type is provided, still show all lengths of that wire type
                if wire_type:
                    for ref, data in inventory.items():
                        if data['type'] == wire_type:
                            search_results[ref] = data
                    if not search_results:
                        message = f"No inventory found for {wire_type}"
                else:
                    message = "Please select a wire type to search"

        # Handle batch delete action
        elif action == 'delete_selected':
            selected_items = request.form.getlist('selected_items')
            if not selected_items:
                message = "No items selected for deletion"
            else:
                deleted_count = 0
                for ref in selected_items:
                    if ref in inventory:
                        del inventory[ref]
                        deleted_count += 1
                if deleted_count > 0:
                    write_inventory(inventory)
                    message = f"Deleted {deleted_count} item(s)"
                else:
                    message = "No matching items found to delete"

        # Handle edit actions
        elif action and action.startswith('edit_'):
            edit_ref = action[5:]  # Remove 'edit_' prefix

        elif action == 'cancel_edit':
            edit_ref = None

        elif action and action.startswith('save_edit_'):
            ref = action[10:]  # Remove 'save_edit_' prefix
            new_quantity = request.form.get('new_quantity')
            if ref in inventory and new_quantity and new_quantity.isdigit():
                inventory[ref]['quantity'] = int(new_quantity)
                write_inventory(inventory)
                message = f"Updated quantity for {ref}"
            edit_ref = None

        elif action == 'delete_quantity':
            delete_ref = request.form.get('delete_ref')
            delete_quantity = request.form.get('delete_quantity')
            if delete_ref and delete_quantity and delete_quantity.isdigit():
                delete_quantity = int(delete_quantity)
                if delete_ref in inventory:
                    if inventory[delete_ref]['quantity'] > delete_quantity:
                        inventory[delete_ref]['quantity'] -= delete_quantity
                        message = f"Removed {delete_quantity} item(s) from {delete_ref}"
                    else:
                        del inventory[delete_ref]
                        message = f"Removed {delete_ref} from inventory"
                    write_inventory(inventory)
                else:
                    message = "Item not found in inventory"
            else:
                message = "Invalid delete request"

        elif action == 'delete_selected':
            selected_refs = request.form.getlist('selected_refs')
            for ref in selected_refs:
                if ref in inventory:
                    del inventory[ref]
            write_inventory(inventory)
            message = f"Deleted {len(selected_refs)} items from inventory"

        elif action == 'delete_selected_types':
            selected_refs = request.form.getlist('selected_refs')
            if not selected_refs:
                message = "No items selected for type deletion"
            else:
                # Get wire types from selected references
                wire_types = set()
                for ref in selected_refs:
                    if ref in inventory:
                        wire_types.add(inventory[ref]['type'])

                # Delete all entries with matching wire types
                deleted_count = 0
                for ref in list(inventory.keys()):
                    if inventory[ref]['type'] in wire_types:
                        del inventory[ref]
                        deleted_count += 1

                write_inventory(inventory)
                message = f"Deleted {deleted_count} items of selected type(s) from inventory"

    return render_template('index.html',
                         inventory=inventory,
                         message=message,
                         search_results=search_results,
                         edit_ref=edit_ref,
                         cable_categories=cable_categories,
                         wire_types=wire_types,
                         lengths=lengths)

if __name__ == '__main__':
    app.run(debug=True)
