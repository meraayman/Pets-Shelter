# Pet Adoption System 

## Start it

1. Install **Python 3.9 or newer** from https://www.python.org/downloads/
   On Windows, tick **"Add python.exe to PATH"** on the first installer screen.
2. Start the app:
   - **Windows:** double-click `run_windows.bat`
   - **Mac / Linux:** open a terminal in this folder and run `./run_mac_linux.sh`
3. Your browser opens at **http://127.0.0.1:5000**. Staff sign in at **http://127.0.0.1:5000/login**.

The first start installs Flask (internet needed once). After that it starts in a couple of seconds.
Close the black window, or press `Ctrl+C`, to stop it.

## Signing in

Your data from the old system is already in `instance/petadoption.db`, including the **admin**
account with the same password you used before. Old passwords are upgraded to the new format
the first time each person signs in.

Forgot the password? With the app stopped, run:

```
python app.py reset-password admin
```

(On Windows, if you used the .bat file: `.venv\Scripts\python app.py reset-password admin`.)

If you ever start with an empty database, the default login is **admin / admin123**. You'll be
reminded to change it.

## Using it on other computers in your network

```
python app.py --lan
```

Other devices can then open `http://<this computer's IP address>:5000`. This built-in server is
fine for a shelter's own network. To put it on the internet, run it behind a proper web server
(for example Waitress or Gunicorn with HTTPS) instead.

## Where things are

| What | Where |
|---|---|
| All data | `instance/petadoption.db` |
| Photos and documents | `uploads/` |
| Backups made from the Backups page | `instance/backups/` |
| Page layouts (HTML) | `templates/` |
| Styles and scripts | `static/` |
| Python code | `petapp/` |

To move the system to another computer, copy the whole folder.

## Bringing in data from a newer MySQL export

The included data came from `database/inet_pet_adoption_db.sql` in the old project. If you have a
newer export from phpMyAdmin:

```
python app.py import-mysql path/to/export.sql
```

Then copy the old upload folders into `uploads/`:

| Old PHP folder | New folder |
|---|---|
| `pages/pet/pet_profile_upload` | `uploads/pets` |
| `pages/pet/health_history_upload` | `uploads/health` |
| `pages/pet/vaccination_proof_upload` | `uploads/vaccination` |
| `pages/pet_owner/pet_owner_upload` | `uploads/owners` |
| `pages/adopter/adopter_upload` | `uploads/adopters` |
| `pages/user/user_upload` | `uploads/users` |
| `pages/companyinfo/logo` | `uploads/logo` |

## What changed from the PHP version

- **Runs anywhere Python runs**, with the database in one file.
- **Reports now work**: adoption status, health and vaccination, pets by type, and pet owners.
  Each can be printed or downloaded as a CSV for Excel.
- **Inquiries**: messages from the public contact page are saved and listed for staff.
- **Backups** are a .zip with the database *and* all uploaded files, for admins only.
- **Security**: every page and action checks sign-in; admin-only areas check the role;
  all forms are protected against cross-site request forgery; deletes need a confirmed POST;
  uploads are checked by content, not just extension; staff documents need sign-in to open;
  repeated wrong passwords lock the login for 5 minutes.
- **Fixes**: pet types and owners that are still in use can't be deleted (which used to hide
  pets from the list); editing a pet no longer resets its registration date; pets with the
  same name no longer overwrite each other's photos.
- The unused Barangay module was left out.

## Accounts for adopters and pet owners

The public site now has a **Sign in** menu with three choices:

- **Adopters** can create their own account, request pets from a pet's profile, and follow each
  request (waiting, approved or not approved) under **My account**. They can cancel a request
  that's still waiting and update their contact details and password.
- **Pet owners** are set up by staff under **Pet owners**. When they sign in they see the pets
  they brought in and whether each has been adopted.
- **Shelter staff** sign in at `/login`, as before.

Accounts imported from the old system keep their passwords. If an owner or adopter has forgotten
theirs, a staff member can set a new one on their Edit page.

## The adoption workflow for staff

1. **Adoption requests** (the menu badge shows how many are waiting): approve or decline each
   request, with an optional note the adopter can read. Approving puts the pet on hold.
2. **Record adoption**: from an approved request, or from **Adoptions > Record adoption** for
   walk-ins. Choose the pet, the adopter and the date, and attach the signed papers if you have
   them. The pet is marked as adopted, and anyone else who requested it is told automatically.
3. Made a mistake? **Undo** on the Adoptions page removes the record and makes the pet available again.

Adoptions also appear on the dashboard and in the new **Completed adoptions** report.

## Signing out

Staff: the **Sign out** button is at the top right of every dashboard page, and at the bottom of
the menu. Adopters and owners: **Sign out** is at the top right of the public site.
