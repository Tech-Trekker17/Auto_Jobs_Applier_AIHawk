import os
import re
import sys
import requests
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from lib_resume_builder_AIHawk import Resume, FacadeManager, ResumeGenerator, StyleManager
from src.utils import chrome_browser_options
from src.llm.llm_manager import GPTAnswerer
from src.aihawk_authenticator import AIHawkAuthenticator
from src.aihawk_bot_facade import AIHawkBotFacade
from src.aihawk_job_manager import AIHawkJobManager
from src.job_application_profile import JobApplicationProfile
from loguru import logger

# --- WhatsApp Reporting Logic ---
def send_whatsapp_update(parameters, status_message):
    """Sends a professional status update to Afry's phone via Koyeb bot"""
    webhook_url = "https://inadequate-hatti-afry-aaa0fa92.koyeb.app/webhook"
    
    payload = {
        "message": f"🤖 *AI Job Agent Update*\n\n"
                   f"📍 *Market:* Dubai, Sharjah, Abu Dhabi\n"
                   f"📢 *Status:* {status_message}\n"
                   f"⏱️ *Time:* {Path('/etc/timezone').read_text().strip() if Path('/etc/timezone').exists() else 'UTC'}\n\n"
                   f"Check GitHub Actions for full logs."
    }
    
    try:
        requests.post(webhook_url, json=payload, timeout=10)
        logger.info("WhatsApp update sent successfully.")
    except Exception as e:
        logger.error(f"Could not send WhatsApp update: {e}")

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")

    @staticmethod
    def validate_config(config_yaml_path: Path) -> dict:
        parameters = ConfigValidator.validate_yaml_file(config_yaml_path)
        required_keys = ['remote', 'experienceLevel', 'jobTypes', 'date', 'positions', 'locations', 'distance', 'llm_model_type', 'llm_model']
        for key in required_keys:
            if key not in parameters:
                raise ConfigError(f"Missing key '{key}' in config file {config_yaml_path}")
        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        if 'llm_api_key' not in secrets or not secrets['llm_api_key']:
            raise ConfigError(f"llm_api_key missing or empty in {secrets_yaml_path}")
        return secrets['llm_api_key']

class FileManager:
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")
        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', output_folder)

def init_browser() -> webdriver.Chrome:
    options = chrome_browser_options()
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def create_and_run_bot(parameters, llm_api_key):
    browser = None
    try:
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        with open(parameters['uploads']['plainTextResume'], "r", encoding='utf-8') as file:
            plain_text_resume = file.read()
        
        resume_object = Resume(plain_text_resume)
        resume_generator_manager = FacadeManager(llm_api_key, style_manager, resume_generator, resume_object, Path("data_folder/output"))
        job_application_profile_object = JobApplicationProfile(plain_text_resume)
        
        browser = init_browser()
        login_component = AIHawkAuthenticator(browser)
        apply_component = AIHawkJobManager(browser)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        
        bot = AIHawkBotFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        bot.set_parameters(parameters)
        
        bot.start_login()
        
        if parameters.get('collectMode'):
            logger.info("Starting Data Collection...")
            bot.start_collect_data()
            send_whatsapp_update(parameters, "✅ Data Collection Finished.")
        else:
            logger.info("Starting Job Applications...")
            bot.start_apply()
            send_whatsapp_update(parameters, "🚀 Application Cycle Complete. Check LinkedIn for messages!")

    except WebDriverException as e:
        logger.error(f"WebDriver error: {e}")
        send_whatsapp_update(parameters, "⚠️ Browser Error: Check if your LinkedIn Session Cookie has expired.")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        send_whatsapp_update(parameters, f"❌ Bot Crashed: {str(e)[:50]}...")
    finally:
        if browser:
            browser.quit()

@click.command()
@click.option('--resume', type=click.Path(exists=True), help="Path to resume PDF")
@click.option('--collect', is_flag=True, help="Collect mode only")
def main(collect, resume):
    try:
        data_folder = Path("data_folder")
        secrets_file, config_file, resume_file, output_folder = FileManager.validate_data_folder(data_folder)
        
        parameters = ConfigValidator.validate_config(config_file)
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)
        
        parameters['uploads'] = {'plainTextResume': resume_file}
        if resume: parameters['uploads']['resume'] = resume
        parameters['outputFileDirectory'] = output_folder
        parameters['collectMode'] = collect
        
        create_and_run_bot(parameters, llm_api_key)
    except Exception as e:
        logger.error(f"Initialization error: {e}")

if __name__ == "__main__":
    main()
