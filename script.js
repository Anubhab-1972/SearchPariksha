// Application State
const state = {
  currentTab: 1,
  course: null,
  year: null,
  branch: "",
  selectedExams: [] // Array of exam IDs
};

// Course Durations (in years)
const courseDurations = {
  'B.Sc': 3, 'B.A': 3, 'B.Com': 3, 'BCA': 3, 'LLB': 3,
  'B.Tech': 4, 'B.Pharm': 4,
  'B.Arch': 5,
  'B.Ed': 2, 'M.Tech': 2, 'M.Sc': 2, 'MBA': 2, 'MCA': 2, 'M.A': 2, 'LL.M': 2, 'M.Des': 2
};

// Course Specializations
const courseSpecializations = {
  'B.Com': ['Accounting & Finance', 'Banking & Insurance', 'Taxation', 'Business Analytics', 'Human Resource Management', 'General Commerce'],
  'B.Tech': ['Computer Science / IT', 'Civil Engineering', 'Mechanical Engineering', 'Electrical Engineering', 'Electronics & Communication', 'Biotechnology', 'Chemical Engineering', 'Polymer Science', 'Other / General Engineering'],
  'M.Tech': ['Computer Science / IT', 'Civil Engineering', 'Mechanical Engineering', 'Electrical Engineering', 'Electronics & Communication', 'Biotechnology', 'Chemical Engineering', 'Polymer Science', 'Other / General Engineering'],
  'B.Sc': ['Physics', 'Chemistry', 'Mathematics', 'Statistics', 'Botany', 'Zoology', 'Biotechnology / Life Sciences', 'Computer Science / IT', 'Geology / Earth Sciences', 'General Science'],
  'M.Sc': ['Physics', 'Chemistry', 'Mathematics', 'Statistics', 'Botany', 'Zoology', 'Biotechnology / Life Sciences', 'Computer Science / IT', 'Geology / Earth Sciences', 'General Science'],
  'B.A': ['Economics', 'History', 'Political Science', 'Psychology', 'Sociology', 'English', 'General Arts'],
  'M.A': ['Economics', 'History', 'Political Science', 'Psychology', 'Sociology', 'English', 'General Arts'],
  'M.Des': ['Product Design', 'Visual Communication', 'Interaction Design', 'Animation', 'General Design'],
  'B.Pharm': ['Pharmaceutics', 'Pharmacology', 'Pharmaceutical Chemistry', 'Pharmacognosy', 'General Pharmacy']
};

// Master Database of Exams - loaded dynamically from exams.json
let masterExamsDatabase = [];

// Load exam data from exams.json (updated automatically by Gemini AI every week)
async function loadExamData() {
  try {
    const response = await fetch('exams.json');
    if (!response.ok) throw new Error('Failed to load exams.json');
    masterExamsDatabase = await response.json();
    console.log(`[OK] Loaded ${masterExamsDatabase.length} exams from exams.json`);
  } catch (error) {
    console.error('[ERROR] Could not load exams.json:', error);
    // The array stays empty - the site will show a "no exams" message gracefully
  }
}

// DOM Elements
const btnNext = document.getElementById('btn-next');
const btnBack = document.getElementById('btn-back');
const branchInput = document.getElementById('branch-input');
const examSelectionList = document.getElementById('exam-selection-list');
const finalCatalogueList = document.getElementById('final-catalogue-list');
const suggestBtn = document.getElementById('btn-suggest');
const themeToggleBtn = document.getElementById('theme-toggle');

// Initialize Event Listeners
document.addEventListener('DOMContentLoaded', async () => {
  // Load exam data from JSON file FIRST, then set up the UI
  await loadExamData();

  setupOptionCards('ug-courses', 'course');
  setupOptionCards('pg-courses', 'course');

  branchInput.addEventListener('change', (e) => {
    state.branch = e.target.value;
    validateTab();
  });

  btnNext.addEventListener('click', goNext);
  btnBack.addEventListener('click', goBack);

  themeToggleBtn.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    if (document.body.classList.contains('dark-mode')) {
      themeToggleBtn.innerText = '☀️';
      themeToggleBtn.title = "Toggle Light Mode";
    } else {
      themeToggleBtn.innerText = '🌙';
      themeToggleBtn.title = "Toggle Dark Mode";
    }
  });

  validateTab();
});

function setupOptionCards(containerId, stateKey) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const cards = container.querySelectorAll('.option-card');
  
  cards.forEach(card => {
    card.addEventListener('click', () => {
      if (stateKey === 'course') {
        document.querySelectorAll('#ug-courses .option-card, #pg-courses .option-card').forEach(c => c.classList.remove('selected'));
      } else {
        cards.forEach(c => c.classList.remove('selected'));
      }
      
      card.classList.add('selected');
      state[stateKey] = card.getAttribute('data-val');
      
      if (stateKey === 'course') {
        state.year = null;
        renderYearSelection();
        renderSpecializations();
      }
      
      validateTab();
    });
  });
}

function renderYearSelection() {
  const container = document.getElementById('year-selection');
  if (!container) return;
  container.innerHTML = '';
  
  const duration = courseDurations[state.course] || 4; // default to 4
  
  for(let i = 1; i <= duration; i++) {
    let suffix = 'th';
    if (i === 1) suffix = 'st';
    if (i === 2) suffix = 'nd';
    if (i === 3) suffix = 'rd';
    
    const yearText = `${i}${suffix} Year`;
    const card = document.createElement('div');
    card.className = 'option-card';
    card.setAttribute('data-val', yearText);
    card.innerText = yearText;
    
    card.addEventListener('click', () => {
      container.querySelectorAll('.option-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      state.year = card.getAttribute('data-val');
      validateTab();
    });
    
    container.appendChild(card);
  }

  // Add Graduated option
  const gradCard = document.createElement('div');
  gradCard.className = 'option-card';
  gradCard.setAttribute('data-val', 'Graduated / Completed');
  gradCard.innerText = 'Graduated / Completed';
  gradCard.addEventListener('click', () => {
    container.querySelectorAll('.option-card').forEach(c => c.classList.remove('selected'));
    gradCard.classList.add('selected');
    state.year = gradCard.getAttribute('data-val');
    validateTab();
  });
  container.appendChild(gradCard);
}

function renderSpecializations() {
  const branchWrapper = document.getElementById('branch-input-wrapper');
  if (!branchWrapper) return;
  
  const noBranchCourses = ['BCA', 'LLB', 'MCA', 'LL.M', 'B.Ed', 'B.Arch', 'MBA', 'B.Pharm'];
  if (noBranchCourses.includes(state.course)) {
    branchWrapper.style.display = 'none';
    state.branch = 'General';
    branchInput.value = '';
  } else {
    branchWrapper.style.display = 'block';
    state.branch = ''; // Force user to re-select
    
    // Populate the dropdown
    branchInput.innerHTML = '<option value="">-- Select Specialization --</option>';
    const specs = courseSpecializations[state.course] || ['General'];
    specs.forEach(spec => {
      const opt = document.createElement('option');
      opt.value = spec;
      opt.innerText = spec;
      branchInput.appendChild(opt);
    });
  }
}

function updateHistoryBars() {
  const bars = [
    document.getElementById('history-tab-2'),
    document.getElementById('history-tab-3'),
    document.getElementById('history-tab-4')
  ];

  const htmlParts = [];
  if (state.course) htmlParts.push(`<div class="history-item">🎓 ${state.course}</div>`);
  if (state.year) htmlParts.push(`<div class="history-item">📅 ${state.year}</div>`);
  if (state.branch) htmlParts.push(`<div class="history-item">🔬 ${state.branch}</div>`);

  const innerHTML = htmlParts.join('');
  bars.forEach(bar => {
    if (bar) bar.innerHTML = innerHTML;
  });
}

function validateTab() {
  let isValid = false;
  
  switch(state.currentTab) {
    case 1:
      isValid = state.course !== null;
      break;
    case 2:
      const noBranchCourses = ['BCA', 'LLB', 'MCA', 'LL.M', 'B.Ed', 'B.Arch', 'MBA', 'B.Pharm'];
      if (noBranchCourses.includes(state.course)) {
        isValid = state.year !== null;
      } else {
        isValid = state.year !== null && state.branch !== "";
      }
      break;
    case 3:
      isValid = state.selectedExams.length > 0;
      break;
    case 4:
      isValid = false; // Final tab, next disabled
      break;
  }

  btnNext.disabled = !isValid;
}

// Complex Filtering Logic based on Branch & Course
function getRelevantExams() {
  const branch = state.branch;
  const isEngineering = state.course === 'B.Tech' || state.course === 'B.E' || state.course === 'M.Tech';
  const isScience = state.course === 'B.Sc' || state.course === 'M.Sc';
  const isArtsComm = state.course === 'B.A' || state.course === 'B.Com' || state.course === 'M.A' || state.course === 'B.Ed';
  
  // Generic Govt/Banking Exams applicable to almost everyone
  const govtExams = ['upsc_cse', 'ssc', 'sbi_po', 'ibps_po', 'rrb_ntpc_grad', 'rrb_ntpc_ug', 'ibacio'];
  const basicGovtExams = ['ssc_chsl', 'rrb_ntpc_ug', 'ssc'];
  
  let validIds = [];

  // Pharmacy
  if (state.course === 'B.Pharm' || state.course === 'M.Pharm') {
    validIds = ['gpat', 'niper', 'gate_bt', ...govtExams];
  }
  // Biotech & Life Sciences
  else if (branch === 'Biotechnology' || branch === 'Botany' || branch === 'Zoology' || branch === 'Biotechnology / Life Sciences') {
    validIds = ['gate_bt', 'gate_xl', 'gate_ey', 'csir', 'vitmee', 'tifr', 'gatb', 'dbt', 'gpat', 'niper', 'barc', ...govtExams];
  }
  // Geology / Earth Sciences
  else if (branch === 'Geology / Earth Sciences') {
    validIds = ['csir', 'barc', ...govtExams];
  }
  // Computer Science & IT
  else if (branch === 'Computer Science / IT') {
    validIds = ['gate_cs', 'gate_da', 'vitmee', 'tifr', 'barc', ...govtExams]; 
  }
  // Civil Engineering
  else if (branch === 'Civil Engineering') {
    validIds = ['gate_ce', 'gate_es', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Mechanical Engineering
  else if (branch === 'Mechanical Engineering') {
    validIds = ['gate_me', 'gate_pi', 'gate_xe', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Electrical Engineering
  else if (branch === 'Electrical Engineering') {
    validIds = ['gate_ee', 'gate_in', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Electronics & Communication
  else if (branch === 'Electronics & Communication') {
    validIds = ['gate_ec', 'gate_in', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Chemical Engineering
  else if (branch === 'Chemical Engineering') {
    validIds = ['gate_cy', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Polymer Science
  else if (branch === 'Polymer Science') {
    validIds = ['gate_xe', 'gate_ch', 'barc', 'aai_atc', ...govtExams];
  }
  // Statistics
  else if (branch === 'Statistics') {
    validIds = ['gate_st', 'csir', ...govtExams];
  }
  // Mathematics
  else if (branch === 'Mathematics') {
    validIds = ['gate_ma', 'csir', 'tifr', ...govtExams];
  }
  // Physics
  else if (branch === 'Physics') {
    validIds = ['gate_ph', 'csir', 'tifr', 'barc', ...govtExams];
  }
  // Chemistry
  else if (branch === 'Chemistry') {
    validIds = ['gate_cy', 'csir', 'tifr', 'barc', ...govtExams];
  }
  // Commerce Branches
  else if (['Accounting & Finance', 'Banking & Insurance', 'Taxation', 'General Commerce'].includes(branch)) {
    validIds = ['ugc', 'sbi_po', 'ibps_po', 'rrb_ntpc_grad', 'rrb_ntpc_ug', 'ssc', 'upsc_cse', 'ibacio', 'ctet'];
  }
  // Management & Analytics
  else if (['Business Analytics', 'Human Resource Management'].includes(branch)) {
    validIds = ['ugc', 'sbi_po', 'ibps_po', 'ssc', 'upsc_cse', 'ctet'];
  }
  // Arts Branches
  else if (['Economics', 'History', 'Political Science', 'Psychology', 'Sociology', 'English', 'General Arts'].includes(branch)) {
    validIds = ['ugc', 'upsc_cse', 'ssc', 'ssc_chsl', 'sbi_po', 'ibps_po', 'rrb_ntpc_grad', 'rrb_ntpc_ug', 'ibacio', 'ctet'];
  }
  // Design
  else if (['Product Design', 'Visual Communication', 'Interaction Design', 'Animation', 'General Design'].includes(branch)) {
    validIds = ['ugc', ...basicGovtExams];
  }
  // Generic Engineering Fallback
  else if (isEngineering) {
    validIds = ['gate_general', 'ies', 'vitmee', 'barc', ...govtExams];
  }
  // Generic Science Fallback
  else if (isScience) {
    validIds = ['csir', 'tifr', 'vitmee', 'barc', ...govtExams, 'ctet'];
  }
  // Arts, Commerce, Education, General Degrees
  else if (isArtsComm) {
    validIds = ['ugc', ...govtExams, 'ssc_chsl', 'ctet'];
  }
  // Ultimate Fallback
  else {
    validIds = ['ugc', ...govtExams, ...basicGovtExams, 'ctet'];
  }

  // Remove duplicates just in case
  validIds = [...new Set(validIds)];

  // Add AAI ATC JE for eligible candidates
  // Eligibility: Any B.E/B.Tech OR B.Sc with Physics/Maths
  if (isEngineering || (isScience && ['Physics', 'Mathematics', 'Statistics', 'Computer Science / IT'].includes(branch))) {
    validIds.push('aai_atc');
  }

  return masterExamsDatabase.filter(exam => validIds.includes(exam.id));
}

function evaluateEligibility(examId) {
  const yearText = state.year;
  const course = state.course;
  if (!yearText) return { eligible: true };
  
  if (yearText === 'Graduated / Completed') {
    return { eligible: true };
  }
  
  const yearNum = parseInt(yearText);
  const duration = courseDurations[course] || 4;
  const isFinalYear = (yearNum === duration);
  const isPG = ['M.Tech', 'M.Sc', 'MBA', 'MCA', 'M.A', 'LL.M', 'M.Des', 'B.Ed'].includes(course);
  
  // CSIR NET / UGC NET
  if (examId === 'csir' || examId === 'ugc') {
    if (isPG) return { eligible: true };
    if (duration >= 4 && isFinalYear) return { eligible: true }; // 4-Year UG Final Year
    return { eligible: false, message: 'Eligible in PG or 4-Year UG Final Year' };
  }
  
  // GATE
  if (examId.startsWith('gate_')) {
    if (isPG) return { eligible: true };
    if (yearNum >= 3) return { eligible: true };
    return { eligible: false, message: 'Eligible from 3rd Year' };
  }
  
  // Final Year / Awaiting Result
  const finalYearExams = ['vitmee', 'ies', 'dbt', 'tifr', 'gatb', 'upsc_cse', 'sbi_po', 'ssc', 'rrb_ntpc_grad', 'niper', 'gpat', 'barc', 'ctet'];
  if (finalYearExams.includes(examId)) {
    if (isFinalYear || (isPG && yearNum === duration)) return { eligible: true };
    return { eligible: false, message: 'Eligible in Final Year' };
  }
  
  // Strict degree in hand
  const degreeExams = ['ibps_po', 'ibacio'];
  if (degreeExams.includes(examId)) {
    return { eligible: false, message: 'Requires Graduation' };
  }
  
  // 12th pass (Eligible anytime during UG/PG)
  const ugExams = ['ssc_chsl', 'rrb_ntpc_ug'];
  if (ugExams.includes(examId)) {
    return { eligible: true };
  }
  
  return { eligible: true };
}

function renderTab3Exams() {
  examSelectionList.innerHTML = '';
  state.selectedExams = []; 

  const relevantExams = getRelevantExams();

  if (relevantExams.length === 0) {
    examSelectionList.innerHTML = '<p style="text-align:center;">No specific exams mapped. Proceed to explore general options.</p>';
    return;
  }

  relevantExams.forEach(exam => {
    const eligibility = evaluateEligibility(exam.id);
    
    const item = document.createElement('div');
    item.className = 'exam-item';
    
    if (!eligibility.eligible) {
      item.classList.add('locked');
      item.style.opacity = '0.5';
      item.style.pointerEvents = 'none';
      item.innerHTML = `
        <label>
          <input type="checkbox" value="${exam.id}" disabled>
          <span>${exam.name}</span>
        </label>
        <span class="exam-date" style="color:#d9534f; font-weight:bold;">🔒 ${eligibility.message}</span>
      `;
    } else {
      const isOpen = exam.dateStr && exam.dateStr.toLowerCase().includes("registration open");
      const liveBadge = isOpen ? `<span class="live-badge">LIVE<span class="live-indicator"></span></span>` : '';

      item.innerHTML = `
        <label>
          <input type="checkbox" value="${exam.id}">
          <span>${exam.name} <a href="#" onclick="openExamDirectory('${exam.name}'); return false;" style="color: #007bff; text-decoration: underline; font-size: 0.8em; margin-left: 8px;">Know about your exam</a></span>
        </label>
        <span class="exam-date">${liveBadge}${exam.dateStr}</span>
      `;

      const checkbox = item.querySelector('input');
      checkbox.addEventListener('change', (e) => {
        if (e.target.checked) {
          state.selectedExams.push(exam.id);
        } else {
          state.selectedExams = state.selectedExams.filter(id => id !== exam.id);
        }
        validateTab();
      });
    }

    examSelectionList.appendChild(item);
  });
}

function renderTab4Catalogue() {
  finalCatalogueList.innerHTML = '';
  
  const finalExams = masterExamsDatabase.filter(exam => state.selectedExams.includes(exam.id));
  
  if (finalExams.length === 0) {
    finalCatalogueList.innerHTML = '<p style="text-align:center; color: var(--text-muted);">No specific exams selected. Please go back and choose exams.</p>';
    return;
  }

  const coreExams = finalExams.filter(exam => exam.category === 'Core Science & Engineering');
  const govtExams = finalExams.filter(exam => exam.category === 'Government & Banking');

  const renderSection = (title, examsArray) => {
    if (examsArray.length === 0) return;

    const sectionTitle = document.createElement('h3');
    sectionTitle.innerText = title;
    sectionTitle.style.marginTop = '20px';
    sectionTitle.style.marginBottom = '10px';
    sectionTitle.style.color = 'var(--text-main)';
    sectionTitle.style.borderBottom = '1px solid var(--border-color)';
    sectionTitle.style.paddingBottom = '5px';
    finalCatalogueList.appendChild(sectionTitle);

    examsArray.forEach(exam => {
      const item = document.createElement('div');
      item.className = 'exam-item';
      item.style.flexDirection = 'column';
      item.style.alignItems = 'flex-start';
      item.style.gap = '10px';

      // Generate calendar link for every exam
      const calLink = getGoogleCalendarLink(exam);
      let btnText = "📅 Add Notification Reminder to Google Calendar";
      if (!exam.hasExactDate && exam.calDate) {
        btnText = "📅 Set Reminder to Check Notification Status";
      }
      
      const calBtnHtml = `
        <a href="${calLink}" target="_blank" class="calendar-btn">
          ${btnText}
        </a>
      `;

      const isOpen = exam.dateStr && exam.dateStr.toLowerCase().includes("registration open");
      const liveBadge = isOpen ? `<span class="live-badge">LIVE<span class="live-indicator"></span></span>` : '';

      item.innerHTML = `
        <div style="width: 100%;">
          <div style="font-size: 1.1em; font-weight: 600; color: var(--text-main); margin-bottom: 5px;">
            ${exam.name} <a href="#" onclick="openExamDirectory('${exam.name}'); return false;" style="color: #007bff; text-decoration: underline; font-size: 0.8em; margin-left: 8px;">Know about your exam</a>
          </div>
          <div style="color: var(--text-muted); font-size: 0.9em; margin-bottom: 5px;">
            ${exam.desc}
          </div>
          <div style="color: var(--text-main); font-weight: bold; font-size: 0.95em; margin-bottom: 15px;">
            ${liveBadge}${exam.dateStr}
          </div>
          ${calBtnHtml}
        </div>
      `;
      finalCatalogueList.appendChild(item);
    });
  };

  renderSection('Core Science & Engineering', coreExams);
  renderSection('Government & Banking', govtExams);
}

function getGoogleCalendarLink(exam) {
  // Only called if exam.hasExactDate is true.
  // Using a fallback date here just in case.
  const d = new Date(exam.calDate || new Date());
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  
  const dateStrUrl = `${year}${month}${day}/${year}${month}${day}`;
  
  let eventTitle = `Reminder: ${exam.name} Notification`;
  if (!exam.hasExactDate) {
      eventTitle = `Check ${exam.name} Registration Status`;
  } else if (exam.dateStr && exam.dateStr.toLowerCase().includes("last date")) {
      eventTitle = `URGENT: Apply for ${exam.name} (Deadline Approaching)`;
  }
  
  const text = encodeURIComponent(eventTitle);
  const details = encodeURIComponent(`${exam.dateStr}. Check the official website.\n\nGenerated via SearchPariksha.`);
  
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${text}&dates=${dateStrUrl}&details=${details}`;
}

function showTab(index) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`tab-${index}`).classList.add('active');
  
  btnBack.style.visibility = index === 1 ? 'hidden' : 'visible';
  
  const homeBtn = document.getElementById('home-btn');
  if (homeBtn) {
    homeBtn.style.display = index === 1 ? 'none' : 'flex';
  }
  
  // Auto-scroll to top ONLY for mobile screens
  if (window.innerWidth <= 768) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  
  // Show the "Know Your Exams" widget ONLY on tabs 3 and 4
  const infoWidget = document.querySelector('.info-widget');
  if (infoWidget) {
    infoWidget.style.display = (index === 3 || index === 4) ? 'block' : 'none';
  }
  
  updateHistoryBars();
  validateTab();
}

function goHome() {
  state.currentTab = 1;
  state.selectedCourse = null;
  state.selectedYear = null;
  state.selectedBranch = null;
  state.selectedExams = [];
  
  // Reset UI elements
  document.querySelectorAll('.option-card').forEach(c => c.classList.remove('selected'));
  document.querySelectorAll('.year-card').forEach(c => c.classList.remove('selected'));
  const branchInput = document.getElementById('branch-input');
  if (branchInput) branchInput.value = "";
  
  showTab(1);
}

document.getElementById('home-btn').addEventListener('click', goHome);

function goNext() {
  if (state.currentTab === 2) {
    renderTab3Exams();
  } else if (state.currentTab === 3) {
    renderTab4Catalogue();
  }
  
  if (state.currentTab < 4) {
    state.currentTab++;
    showTab(state.currentTab);
  }
}

function goBack() {
  // If we are in Tab 5, returning takes us back to our previous tab
  if (document.getElementById('tab-5').classList.contains('active')) {
    document.getElementById('tab-5').classList.remove('active');
    showTab(state.currentTab);
    return;
  }
  
  if (state.currentTab > 1) {
    state.currentTab--;
    showTab(state.currentTab);
  }
}

// --- Exam Directory (Tab 5) Logic ---
const directoryList = document.getElementById('directory-list');
const examSearchInput = document.getElementById('exam-search');
const browseDirectoryBtn = document.getElementById('browse-directory-btn');

function renderExamDirectory(searchTerm = "") {
  if (!directoryList) return;
  directoryList.innerHTML = '';
  const term = searchTerm.toLowerCase();
  
  const filteredExams = masterExamsDatabase.filter(exam => 
    exam.name.toLowerCase().includes(term) || 
    exam.desc.toLowerCase().includes(term) ||
    exam.category.toLowerCase().includes(term)
  );

  if (filteredExams.length === 0) {
    directoryList.innerHTML = '<p style="text-align:center; color: var(--text-muted);">No exams found matching your search.</p>';
    return;
  }

  filteredExams.forEach(exam => {
    const item = document.createElement('div');
    item.className = 'exam-item';
    item.style.flexDirection = 'column';
    item.style.alignItems = 'flex-start';
    item.style.gap = '8px';

    const isOpen = exam.dateStr && exam.dateStr.toLowerCase().includes("registration open");
    const liveBadge = isOpen ? `<span class="live-badge">LIVE<span class="live-indicator"></span></span>` : '';

    item.innerHTML = `
      <div style="font-size: 1.1em; font-weight: 600; color: var(--text-main);">
        ${exam.name}
      </div>
      <div style="color: var(--text-muted); font-size: 0.9em;">
        ${exam.desc}
      </div>
      <div style="color: var(--text-main); font-weight: bold; font-size: 0.95em;">
        ${liveBadge}${exam.dateStr}
      </div>
    `;
    directoryList.appendChild(item);
  });
}

function openExamDirectory(searchTerm = "") {
  // Hide current tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  // Show Tab 5
  document.getElementById('tab-5').classList.add('active');
  
  // Set back button so they can return
  btnBack.style.visibility = 'visible';
  
  // Setup search
  if (examSearchInput) {
    examSearchInput.value = searchTerm;
  }
  renderExamDirectory(searchTerm);
}

// Event Listeners for Directory
if (examSearchInput) {
  examSearchInput.addEventListener('input', (e) => {
    renderExamDirectory(e.target.value);
  });
}

if (browseDirectoryBtn) {
  browseDirectoryBtn.addEventListener('click', () => {
    openExamDirectory("");
  });
}
