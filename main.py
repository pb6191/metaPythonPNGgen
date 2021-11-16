import os
import shutil
import time
from io import BytesIO
from os import environ
import csv
import re

from flask import (
    Flask,
    Response,
    render_template,
    request,
    send_file,
    stream_with_context,
)
from PIL import Image, ImageOps
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", message="")


@app.route("/download/", methods=["POST"])
def download():
    return send_file("cards.zip", as_attachment=True, download_name="cards.zip")


@app.route("/manual_download/", methods=["GET"])
def manual_download():
    if os.path.isdir("extractedImgs"):
        shutil.make_archive("cards", "zip", "extractedImgs")
    if os.path.exists("cards.zip"):
        return send_file("cards.zip", as_attachment=True, download_name="cards.zip")
    else:
        return "Whoops, something went wrong."


def write_csv(header, data, path, mode):
    with open(path, mode) as f:
        writer = csv.writer(f)
        if mode == "w":
            writer.writerow(header)
        writer.writerows(data)


@app.route("/status/", methods=["POST"])
def status():
    def generate():
        msg = "<p>If you want to generate cards manually, visit <a href='https://metatags.io/' target='_blank'>metatags.io</a> or <a href='https://socialsharepreview.com' target='_blank'>socialsharepreview.com</a>.</p><p>A download button will appear at the bottom of the page when all URLs have been processed. But if you want to terminate the app and download the URLs/cards that have already been processed, click <a href='/manual_download/'>here</a>.</p>"
        text = request.form["text"]
        if not text:
            yield "Please provide URLs." + msg
            return None
        yield "Initializing..." + msg

        # implicit waits and parallelization
        chrome_options = webdriver.ChromeOptions()
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("enable-automation")
        driver = webdriver.Chrome(
            executable_path=os.environ.get("CHROMEDRIVER_PATH"), options=chrome_options
        )
        driver.implicitly_wait(5)
        x = 3840
        y = x / 16 * 10
        driver.set_window_size(x, y)
        driver.delete_all_cookies()
        url = "https://metatags.io/"
        driver.get(url)
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[contains(@class, 'search')]")
            )
        )
        time.sleep(5)
        driver.execute_script("document.body.style.zoom = '150%'")
        driver.execute_script(
            """
            const fbElement = document.querySelector("div.card-seo-facebook");
            fbElement.style = "border-radius:5.99998px";
            const ipElement = document.querySelector("section.nav-search");
            document.body.innerHTML = "";
            document.body.appendChild(fbElement);
            document.body.appendChild(ipElement);
            """
        )
        if os.path.isdir("extractedImgs"):
            shutil.rmtree("extractedImgs")
        if os.path.exists("cards.zip"):
            os.remove("cards.zip")
        os.mkdir("extractedImgs", 0o777)

        headlines = text.splitlines()
        headlines = list(filter(None, headlines))
        headlines = list(set(headlines))
        yield f"Processing {len(headlines)} unique urls<br><br>"
        for i, h in enumerate(headlines, start=1):
            h = h.strip().strip("/")
            print(i, h)
            yield f"Processing url {i} of {len(headlines)}: {h}<br>"
            driver.find_element(By.XPATH, "//input[contains(@class, 'search')]").clear()
            driver.find_element(
                By.XPATH, "//input[contains(@class, 'search')]"
            ).send_keys(h)
            driver.find_element(
                By.XPATH, "//input[contains(@class, 'search')]"
            ).send_keys(Keys.RETURN)
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[@class = 'card-seo-facebook']")
                )
            )
            time.sleep(10)

            im = driver.get_screenshot_as_png()
            im = Image.open(BytesIO(im))
            im1 = im.crop((0, 0, x / 5.12, x / 7.524))
            im1 = ImageOps.expand(im1, border=5, fill=(255, 255, 255))

            # get image title name
            title = driver.find_element(
                By.XPATH, "/html/body/div/div[2]/div/div/div"
            ).text
            title = re.sub(r"\W+", " ", title)
            title = re.sub(r" \w ", " ", title).strip()
            title = title.replace(" ", "-")[:100].lower()

            if len(title) < 3:  # in case there are problems with the title text
                name = (h.split("?")[0].split("/")[-1]).replace(".html", "")
                filename = name + ".png"
            else:
                filename = title + ".png"
            im1.save("extractedImgs/" + filename, "png")

            yield f"Output: {filename}<br><br>"

            if i == len(headlines):
                yield "<br>Done. cards.zip is ready for download. See <strong>_cards_.csv</strong> in the zipped folder for details.<br>"
            else:
                time.sleep(1)

            mode = "w" if i == 1 else "a"
            write_csv(
                header=["url", "filename"],
                data=zip([h], [filename]),
                path=os.path.join("extractedImgs", "_cards_.csv"),
                mode=mode,
            )

        driver.quit()
        shutil.make_archive("cards", "zip", "extractedImgs")
        shutil.rmtree("extractedImgs")
        yield render_template("index2.html")

    return Response(stream_with_context(generate()))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=environ.get("PORT", 5000))
