const loginForm =
document.getElementById("loginForm");

const loginBtn =
document.getElementById("loginBtn");

const logoSpin =
document.getElementById("logoSpin");

/* ==========================
   BUBBLE EXPLOSION
========================== */

function createBubbleExplosion() {

  const totalBubbles = 150;

  for(let i = 0; i < totalBubbles; i++){

    const bubble =
    document.createElement("div");

    bubble.classList.add(
      "blast-bubble"
    );

    /* Random size */
    const size =
    Math.random() * 50 + 10;

    bubble.style.width =
    `${size}px`;

    bubble.style.height =
    `${size}px`;

    /* Start from center */
    bubble.style.left =
    "50%";

    bubble.style.top =
    "50%";

    /* Random pastel colors */
    const colors = [
      "rgba(168,85,247,.25)",
      "rgba(236,72,153,.25)",
      "rgba(96,165,250,.25)",
      "rgba(255,210,80,.22)",
      "rgba(255,255,255,.25)"
    ];

    bubble.style.background =
    colors[
      Math.floor(
        Math.random() *
        colors.length
      )
    ];

    document.body.appendChild(
      bubble
    );

    /* SAFE movement */
    const x =
    (Math.random() - 0.5)
    * window.innerWidth;

    const y =
    (Math.random() - 0.5)
    * window.innerHeight;

    requestAnimationFrame(() => {

      bubble.style.transform =
      `translate(${x}px,
      ${y}px) scale(1.8)`;

      bubble.style.opacity =
      "0";
    });

    setTimeout(() => {
      bubble.remove();
    }, 2800);
  }
}

/* ==========================
   LOGIN
========================== */

loginForm.addEventListener("submit", async function(e) {
  e.preventDefault();
  
  const emailVal = document.getElementById("email").value.trim();
  const passwordVal = document.getElementById("password").value.trim();

  loginBtn.disabled = true;
  loginBtn.innerHTML = "Authenticating...";
  loginBtn.style.opacity = "0.8";
  logoSpin.classList.add("spinning");

  try {
    const response = await fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: emailVal, password: passwordVal })
    });
    const data = await response.json();

    if (data.success) {
      createBubbleExplosion();
      
      setTimeout(() => {
        loginBtn.innerHTML = "Welcome to NeXa ✨";
      }, 1000);

      setTimeout(() => {
        window.location.href = "/main";
      }, 2200);
    } else {
      logoSpin.classList.remove("spinning");
      loginBtn.disabled = false;
      loginBtn.innerHTML = "Log in to NeXa";
      loginBtn.style.opacity = "1";
      alert(data.message || "Invalid credentials.");
    }
  } catch (error) {
    logoSpin.classList.remove("spinning");
    loginBtn.disabled = false;
    loginBtn.innerHTML = "Log in to NeXa";
    loginBtn.style.opacity = "1";
    alert("Connection error. Is the server running?");
  }
});