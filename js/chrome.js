(() => {
  const path = (location.pathname || "").replace(/\\/g, "/");
  const inSubdir = /\/(news|encyclopedia|members)\/[^/]+$/.test(path);
  const r = inSubdir ? "../" : "";

  const header = `
  <header class="site-header">
    <div class="header-bar">
      <div class="wrap">
        <span class="header-meta">Aichach, Germany</span>
        <div class="header-bar-links">
          <a href="tel:+918130673015">+91 81306 73015</a>
          <a href="mailto:iccppglobal@gmail.com">iccppglobal@gmail.com</a>
          <div class="lang-switch" role="group" aria-label="Language">
            <button type="button" class="lang-btn" data-lang="en" aria-label="Switch to English" title="English">
              <svg viewBox="0 0 60 30" aria-hidden="true" focusable="false">
                <clipPath id="iccpp-uk"><path d="M0,0v30h60V0z"/></clipPath>
                <path d="M0,0v30h60V0z" fill="#012169"/>
                <path d="M0,0 60,30 M60,0 0,30" stroke="#fff" stroke-width="6" clip-path="url(#iccpp-uk)"/>
                <path d="M0,0 60,30 M60,0 0,30" stroke="#C8102E" stroke-width="4" clip-path="url(#iccpp-uk)"/>
                <path d="M30,0v30M0,15h60" stroke="#fff" stroke-width="10"/>
                <path d="M30,0v30M0,15h60" stroke="#C8102E" stroke-width="6"/>
              </svg>
            </button>
            <button type="button" class="lang-btn" data-lang="de" aria-label="Switch to German" title="Deutsch">
              <svg viewBox="0 0 5 3" aria-hidden="true" focusable="false">
                <rect width="5" height="1" y="0" fill="#000"/>
                <rect width="5" height="1" y="1" fill="#DD0000"/>
                <rect width="5" height="1" y="2" fill="#FFCE00"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
    <div class="wrap header-main">
      <a class="brand" href="${r}index.html">
        <img src="${r}assets/photos/logo-psi.png" alt="ICCPP">
        <span class="brand-text">
          <strong>ICCPP</strong>
          <span>International Centre for Clinical Psychology and Psychotherapy</span>
        </span>
      </a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="Open menu">
        <span></span>
      </button>
      <a class="btn btn-header" href="${r}internships.html">Internship</a>
      <div class="nav-backdrop"></div>
    </div>
      <nav class="site-nav" id="site-nav" aria-label="Primary">
        <ul class="nav-root">
          <li><a href="${r}index.html">Home</a></li>
          <li class="has-sub">
            <a href="${r}mission.html">Mission</a>
            <ul>
              <li><a href="${r}internships.html">Internships</a></li>
              <li><a href="${r}language-course.html">Language Course</a></li>
            </ul>
          </li>
          <li><a href="${r}members.html">Members</a></li>
          <li class="has-sub">
            <a href="${r}documentation.html">Documentation</a>
            <ul class="wide">
              <li><a href="${r}iccpp-books.html">ICCPP Books</a></li>
              <li><a href="${r}encyclopedia.html">Encyclopedia</a></li>
              <li><a href="${r}library.html">Library</a></li>
              <li><a href="${r}books.html">Books</a></li>
              <li class="has-sub">
                <a href="${r}videos.html">Video Documentaries</a>
                <ul>
                  <li><a href="${r}videos-psychodrama.html">Humanistic Psychodrama</a></li>
                  <li><a href="${r}videos-freud.html">Freud – Interpretation of Dreams</a></li>
                  <li><a href="${r}videos-family.html">Systemic Family Therapy</a></li>
                </ul>
              </li>
              <li><a href="${r}journal-psychodrama.html">International Journal of Humanistic Psychodrama</a></li>
              <li><a href="${r}criminology.html">Criminology without borders</a></li>
              <li><a href="${r}forensic-journal.html">Indian Journal of Forensic Medicine and Toxicology</a></li>
              <li><a href="${r}iaps.html">IAPS – Wisdom</a></li>
            </ul>
          </li>
          <li><a href="${r}journal.html">Journal</a></li>
          <li class="has-sub">
            <a href="${r}education.html">Education</a>
            <ul>
              <li><a href="${r}training-psychodrama.html">Training in humanistic psychodrama</a></li>
              <li><a href="${r}psychodrama-india.html">Humanistic Psychodrama in India</a></li>
              <li><a href="${r}gerontological-therapy.html">Gerontological Therapy</a></li>
              <li><a href="${r}assistance.html">Psychological-psychotherapeutic assistance</a></li>
              <li><a href="${r}past-seminars.html">Past Seminars</a></li>
            </ul>
          </li>
          <li class="has-sub">
            <a href="${r}science.html">Science</a>
            <ul>
              <li><a href="${r}expose.html">Exposé</a></li>
              <li><a href="${r}empirical-papers.html">How to structure empirical term papers</a></li>
              <li><a href="${r}thesis-criteria.html">Criteria for the evaluation of theses</a></li>
            </ul>
          </li>
          <li><a href="${r}partners.html">Partners</a></li>
          <li class="has-sub">
            <a href="${r}archive.html">Archive</a>
            <ul class="wide">
              <li class="has-sub">
                <a href="${r}newsletters.html">Newsletter</a>
                <ul>
                  <li><a href="${r}newsletters-1-10.html">Newsletter 1 – 10</a></li>
                  <li><a href="${r}newsletters-11-20.html">Newsletter 11 – 20</a></li>
                  <li><a href="${r}newsletters-21-30.html">Newsletter 21 – 30</a></li>
                </ul>
              </li>
              <li class="has-sub">
                <a href="${r}tour.html">Two students on a tour through Germany</a>
                <ul>
                  <li><a href="${r}tour-1-11.html">Day 1 to 11</a></li>
                  <li><a href="${r}tour-12-21.html">Day 12 to 21</a></li>
                  <li><a href="${r}tour-22-31.html">Day 22 to 31</a></li>
                  <li><a href="${r}tour-32-41.html">Day 32 to 41</a></li>
                </ul>
              </li>
            </ul>
          </li>
          <li><a href="${r}contact.html">Contact</a></li>
        </ul>
      </nav>
  </header>`;

  const footer = `
  <footer class="site-footer">
    <div class="wrap footer-grid">
      <div>
        <h2>ICCPP</h2>
        <p>International Centre for Clinical Psychology and Psychotherapy, in cooperation with Krasnoyarsk State Medical University — Prof. V. F. Voino-Yasenetsky.</p>
        <p>Franz-Beck-Straße 31<br>86551 Aichach, Germany</p>
      </div>
      <div>
        <h3>Visit</h3>
        <ul>
          <li><a href="${r}mission.html">Mission</a></li>
          <li><a href="${r}documentation.html">Documentation</a></li>
          <li><a href="${r}journal.html">Journal</a></li>
          <li><a href="${r}donate.html">Donate</a></li>
          <li><a href="${r}archive.html">Archive</a></li>
        </ul>
      </div>
      <div>
        <h3>Contact</h3>
        <ul>
          <li><a href="tel:+918130673015">+91 81306 73015</a></li>
          <li><a href="mailto:iccppglobal@gmail.com">iccppglobal@gmail.com</a></li>
          <li><a href="${r}contact.html">Contact</a></li>
          <li><a href="${r}privacy.html">Data protection</a></li>
          <li><a href="${r}imprint.html">Imprint</a></li>
        </ul>
      </div>
    </div>
    <div class="wrap footer-bottom">
      <span>Copyright ICCPP. Redesign for educational use.</span>
      <span>English</span>
    </div>
  </footer>
  <button type="button" class="feedback-launch" id="feedback-launch" aria-expanded="false" aria-controls="feedback-panel">Feedback</button>
  <div class="feedback-layer" id="feedback-layer" hidden>
    <div class="feedback-backdrop" data-feedback-close></div>
    <div class="feedback-panel" id="feedback-panel" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
      <button type="button" class="feedback-close" data-feedback-close aria-label="Close">Close</button>
      <p class="kicker">Contact</p>
      <h2 id="feedback-title">Feedback</h2>
      <p>Tell us how we can improve this website. Centre staff will receive your note in the inbox.</p>
      <form class="form" data-validate data-inquiry="feedback" data-success="Thank you. Centre staff have received your feedback.">
        <div class="form-row">
          <label>First name <input name="first" type="text" required></label>
          <label>Last name <input name="last" type="text" required></label>
        </div>
        <label>Email <input name="email" type="email" required></label>
        <label>Message <textarea name="message" rows="4" required></textarea></label>
        <button class="btn" type="submit">Send</button>
        <p class="form-status" role="status"></p>
      </form>
    </div>
  </div>`;

  const skip = document.querySelector(".skip-link");
  const main = document.querySelector("main");
  const headerNode = document.createRange().createContextualFragment(header);
  const footerNode = document.createRange().createContextualFragment(footer);

  if (skip && skip.nextSibling) {
    skip.parentNode.insertBefore(headerNode, skip.nextSibling);
  } else {
    document.body.insertBefore(headerNode, document.body.firstChild);
  }

  if (main && main.nextSibling) {
    main.parentNode.insertBefore(footerNode, main.nextSibling);
  } else {
    document.body.appendChild(footerNode);
  }

  const i18n = document.createElement("script");
  i18n.src = `${r}js/i18n.js?v=12`;
  i18n.async = false;
  document.body.appendChild(i18n);
})();
