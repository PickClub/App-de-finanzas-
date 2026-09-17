#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  MoneyFlow finance app (Expo + FastAPI + Mongo). Recent work:
  1) Debts screen top summary is now a FLIP CARD (front = "Yo debo" / i_owe, back = "Me deben" / they_owe) with corrected per-direction logic.
  2) GLOBAL THEME SYSTEM refactor (reported bug): switching Claro/Oscuro/Sistema must instantly re-theme the WHOLE app (all screens/cards/flip card both faces) with a single source of truth, persist the preference, follow the device in "system", and the Back button must keep working after selecting a theme (previously it reloaded the JS bundle and reset the nav stack).
  3) Dashboard Ingresos/Gastos cards enriched (icon, title, amount, mini bar chart, promedio diario) and made equal height to the accounts % card.

frontend:
  - task: "Global theme system (Claro/Oscuro/Sistema) reactive, persistent, no bundle reload"
    implemented: true
    working: "NA"
    file: "src/theme.ts, app/_layout.tsx, app/settings.tsx, + all screens converted to makeStyles/useTheme"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Replaced boot-time singleton + bundle-reload approach with a React ThemeContext (ThemeProvider) exposing mode/scheme/colors/setMode. All screens converted from module-level StyleSheet.create(colors) to makeStyles((colors)=>...) + useTheme(). setMode only persists + updates state (no reload) so the navigation stack/back button is preserved. Fixed a web hydration bug where async storage overrode the synchronous localStorage value."
  - task: "Settings theme selector + Back button after theme change"
    implemented: true
    working: "NA"
    file: "app/settings.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Theme buttons now call setMode (context) instead of setThemeMode (which reloaded the bundle). Selecting a theme must NOT reset navigation; Back must still return to the previous screen."
  - task: "Debts summary flip card (front Yo debo / back Me deben) theme-aware"
    implemented: true
    working: "NA"
    file: "app/debts/index.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Tap flips 3D between i_owe (front) and they_owe (back). Both faces derive colors from the global theme so they follow light/dark."
  - task: "Dashboard Ingresos/Gastos cards (icon, title, amount, mini bars, promedio diario) equal height to accounts card"
    implemented: true
    working: "NA"
    file: "app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Only internal content of Ingresos/Gastos changed; widths unchanged; heights stretch to equal the accounts % card. Added MiniBars + DragDots + daily average."

  - task: "Navigation animations: faster slide_from_right forward + clean reverse on back (no flash/double animation)"
    implemented: true
    working: "NA"
    file: "app/_layout.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: "Root Stack screenOptions: kept animation 'slide_from_right' (native-stack auto-plays the REVERSE on pop -> current screen exits to the right, previous revealed). Reduced animationDuration 200 -> 160 for a noticeably faster/snappier entry. Changed animationTypeForReplace 'push' -> 'pop' so replace navigations don't flash a forward-entry. Goal: forward fast+smooth, back gets a distinct reverse with no flicker/double-animation/duplicated screen. Needs UI verification of the back-flash fix (cannot be verified via static screenshots)."
  - task: "Amounts display as whole numbers (no decimals) with thousands separators app-wide"
    implemented: true
    working: true
    file: "src/format.ts"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "formatCurrency now rounds to integer and uses maximumFractionDigits:0 with en-US thousands separators (same as existing formatCurrencyInt). Display-only; stored numeric values untouched. Verified on web: dashboard Saldo total $17,052, account cards $2,907/$346/$8,000/$1,500/$2,500/$1,800, transactions -$16/-$45/-$5, Cuentas screen whole numbers. Debt cards already used formatCurrencyInt."
  - task: "Mis cuentas account cards visual redesign (vivid gradient, soft shadow, translucent icon box, arrow button, watermark)"
    implemented: true
    working: true
    file: "app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: "Visual-only redesign of ONLY the individual account cards inside 'Mis cuentas'. Kept 3-col grid, compact size (minHeight 84, flexBasis 31%), position, logic, data, navigation. Added subtle diagonal LinearGradient (lighten16 -> base -> darken06), reduced shadow to a soft short diffuse one (opacity .06 r5 y2), top-left icon in translucent white box, top-right circular chevron button using darken(color,.16), large very-transparent (white 15%) financial watermark of the account icon in bottom-right (overflow hidden clips it). Name semibold 12.5 > balance 11 (less dominant), no decimals, no bottom type labels. Other sections untouched. Verified on web preview."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: true

test_plan:
  current_focus:
    - "Navigation animations: faster slide_from_right forward + clean reverse on back (no flash/double animation)"
    - "Amounts display as whole numbers (no decimals) with thousands separators app-wide"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Please test on the WEB preview. Key scenarios:
        THEME (main reported bug):
          1. Go to Más -> Ajustes. Tap "Oscuro": the ENTIRE app must turn dark (dashboard, cards, headers, tabs, debts flip card BOTH faces, modals). Tap "Claro": entire app light. Tap "Sistema": follows device.
          2. Sequence Claro -> Oscuro -> Claro must never leave any component stuck on the previous theme (check the Debts top flip card especially, and both of its faces).
          3. After selecting ANY theme on the Ajustes screen, the Back button (top-left chevron) MUST still navigate back (it must NOT reset the stack / block navigation). Selecting a theme should NOT reload the app.
          4. Persistence: reload the page after choosing Oscuro -> app should reopen in dark.
        FLIP CARD (Debts): open "Deudas y préstamos"; tap the top summary card -> it flips between "Resumen de deudas" (Yo debo) and "Resumen de préstamos" (Me deben). Front totals: 2 debts, Pendiente 10,200, Total 14,500, Pagado 4,300. Back: 1 cuenta, Pendiente 700, Total 1,000, Recibido 300.
        DASHBOARD: Inicio -> the Ingresos and Gastos cards each show icon + "Este mes" + drag dots + title + amount + mini bar chart + "Promedio diario"; the two cards are the same height as the percentages card to their right and aligned top & bottom.
        Note: there is no auth. Data is seeded. Ignore CORS console noise if loading via a non-canonical domain.
