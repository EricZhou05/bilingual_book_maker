from bs4 import BeautifulSoup as bs
from bs4 import NavigableString
from rich import print
import re
import backoff
import logging
from copy import copy

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class EPUBBookLoaderHelper:
    def __init__(
        self, translate_model, accumulated_num, translation_style, context_flag
    ):
        self.translate_model = translate_model
        self.accumulated_num = accumulated_num
        self.translation_style = translation_style
        self.context_flag = context_flag

    def insert_trans(self, p, text, translation_style="", single_translate=False):
        if text is None:
            text = ""
        if (
            p.string is not None
            and p.string.replace(" ", "").strip() == text.replace(" ", "").strip()
        ):
            return
        new_p = copy(p)
        new_p.clear()
        
        parsed = bs(text, "html.parser")
        if len(parsed.contents) > 0:
            new_p.append(parsed)
        else:
            new_p.append(text)
        
        # fix EPUB duplicate id issue
        if not single_translate and new_p.has_attr('id'):
            del new_p['id']
        if translation_style != "":
            new_p["style"] = translation_style
        p.insert_after(new_p)
        if single_translate:
            p.extract()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_backoff=lambda details: logger.warning(f"retry backoff: {details}"),
        on_giveup=lambda details: logger.warning(f"retry abort: {details}"),
        jitter=None,
    )
    def translate_with_backoff(self, text, context_flag=False):
        return self.translate_model.translate(text, context_flag)

    def deal_new(self, p, wait_p_list, single_translate=False):
        self.deal_old(wait_p_list, single_translate, self.context_flag)
        
        orig_format = str(p)
        sent_format = p.text
        received_text = shorter_result_link(self.translate_with_backoff(sent_format, self.context_flag))
        
        self.insert_trans(
            p,
            received_text,
            self.translation_style,
            single_translate,
        )
        
        assembled_format = str(p) if single_translate else str(p) + "\n" + str(p.next_sibling)
        
        print("[bold cyan]1. 原始格式 (Original Format):[/bold cyan]\n" + orig_format)
        print("[bold cyan]2. 发送格式 (Sent Format):[/bold cyan]\n" + sent_format)
        print(f"[bold cyan]3. 回传文本 (Received Text):[/bold cyan]\n[bold green]{received_text}[/bold green]")
        print(f"[bold cyan]4. 拼装格式 (Assembled Format):[/bold cyan]\n{assembled_format}")
        print("-" * 60)

    def deal_old(self, wait_p_list, single_translate=False, context_flag=False):
        if not wait_p_list:
            return

        texts_to_translate = [
            p.decode_contents(formatter="html") if not isinstance(p, NavigableString) else str(p)
            for p in wait_p_list
        ]
        result_txt_list = self.translate_model.translate_list(texts_to_translate)

        for i in range(len(wait_p_list)):
            if i < len(result_txt_list):
                p = wait_p_list[i]
                orig_format = str(p)
                sent_format = texts_to_translate[i]
                received_text = shorter_result_link(result_txt_list[i])
                
                self.insert_trans(
                    p,
                    received_text,
                    self.translation_style,
                    single_translate,
                )
                
                assembled_format = str(p) if single_translate else str(p) + "\n" + str(p.next_sibling)
                
                print("[bold cyan]1. 原始格式 (Original Format):[/bold cyan]\n" + orig_format)
                print("[bold cyan]2. 发送格式 (Sent Format):[/bold cyan]\n" + sent_format)
                print(f"[bold cyan]3. 回传文本 (Received Text):[/bold cyan]\n[bold green]{received_text}[/bold green]")
                print(f"[bold cyan]4. 拼装格式 (Assembled Format):[/bold cyan]\n{assembled_format}")
                print("-" * 60)

        wait_p_list.clear()


url_pattern = r"(http[s]?://|www\.)+(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"


def is_text_link(text):
    return bool(re.compile(url_pattern).match(text.strip()))


def is_text_tail_link(text, num=80):
    text = text.strip()
    pattern = r".*" + url_pattern + r"$"
    return bool(re.compile(pattern).match(text)) and len(text) < num


def shorter_result_link(text, num=20):
    match = re.search(url_pattern, text)

    if not match or len(match.group()) < num:
        return text

    return re.compile(url_pattern).sub("...", text)


def is_text_source(text):
    return text.strip().startswith("Source: ")


def is_text_list(text, num=80):
    text = text.strip()
    return re.match(r"^Listing\s*\d+", text) and len(text) < num


def is_text_figure(text, num=80):
    text = text.strip()
    return re.match(r"^Figure\s*\d+", text) and len(text) < num


def is_text_digit_and_space(s):
    for c in s:
        if not c.isdigit() and not c.isspace():
            return False
    return True


def is_text_isbn(s):
    pattern = r"^[Ee]?ISBN\s*\d[\d\s]*$"
    return bool(re.match(pattern, s))


def not_trans(s):
    return any(
        [
            is_text_link(s),
            is_text_tail_link(s),
            is_text_source(s),
            is_text_list(s),
            is_text_figure(s),
            is_text_digit_and_space(s),
            is_text_isbn(s),
        ]
    )
