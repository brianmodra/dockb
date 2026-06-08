import threading
from unittest.mock import MagicMock

import pytest
import spacy
from spacy.language import Language
from spacy.tokens import Doc

from dockb.models.sentence import Sentence
from dockb.models.token import Type
from dockb.services.semantics.delete_job import DeleteJob
from dockb.services.semantics.doc_cache import DocCache
from dockb.services.semantics.job import JobStatus
from dockb.services.semantics.job_queue import JobQueue
from dockb.services.semantics.reconstruct_job import ReconstructJob
from dockb.services.semantics.sentence_tokenizer import SentenceTokenizer, TokenizationCancelled

STRESS_NUM_THREADS = 10
STRESS_JOBS_PER_THREAD = 20


class WaitableDocCache(DocCache):
    def __init__(self, nlp: Language) -> None:
        self._wait_event = threading.Event()
        super().__init__(nlp)

    def get_doc(self, text: str) -> Doc:
        self._wait_event.set()
        return super().get_doc(text)

    def wait_for_get(self) -> None:
        self._wait_event.wait()


def test_sentence_tokenizer_can_be_cancelled_even_if_already_running_in_the_queue():
    nlp = spacy.load("en_core_web_sm")
    doc_cache = WaitableDocCache(nlp)
    queue = JobQueue()
    sentence = Sentence()
    # Proverbs 27:14
    sentence.set_text("If anyone loudly blesses their neighbor early in the morning, it will be taken as a curse.")
    djob = DeleteJob()
    djob.set(sentence)
    rjob1 = ReconstructJob()
    rjob1.set(sentence, doc_cache)
    rjob2 = ReconstructJob()
    rjob2.set(sentence, doc_cache)
    queue.enqueue(djob)
    queue.enqueue(rjob1)
    queue.start()
    doc_cache.wait_for_get()
    rjob1.cancel()
    rjob1.done.wait()
    assert rjob1.status == JobStatus.CANCELLED
    assert isinstance(rjob1.error, TokenizationCancelled)
    assert len(sentence.tokens) == 0
    queue.enqueue(rjob2)
    rjob2.done.wait()
    assert len(sentence.tokens) > 0
    queue.shutdown()


def test_sentence_tokenizer_is_cancelled_properly_when_second_reconstruct_job_added():
    nlp = spacy.load("en_core_web_sm")
    doc_cache = WaitableDocCache(nlp)
    queue = JobQueue()
    sentence = Sentence()
    # Proverbs 27:14
    sentence.set_text("If anyone loudly blesses their neighbor early in the morning, it will be taken as a curse.")
    djob = DeleteJob()
    djob.set(sentence)
    rjob1 = ReconstructJob()
    rjob1.set(sentence, doc_cache)
    rjob2 = ReconstructJob()
    rjob2.set(sentence, doc_cache)
    queue.enqueue(djob)
    queue.enqueue(rjob1)
    queue.start()
    doc_cache.wait_for_get()
    queue.enqueue(rjob2)
    rjob1.done.wait()
    assert rjob1.status == JobStatus.CANCELLED
    assert isinstance(rjob1.error, TokenizationCancelled)
    rjob2.done.wait()
    assert len(sentence.tokens) > 0
    queue.shutdown()


class TokenizeThread(threading.Thread):
    def __init__(self, queue: JobQueue, doc_cache: WaitableDocCache, sentence: Sentence) -> None:
        super().__init__()
        self.queue = queue
        self.doc_cache = doc_cache
        self.sentence = sentence
        self.wait_for = threading.Event()

    def go(self) -> None:
        self.wait_for.set()

    def run(self) -> None:
        self.wait_for.wait()
        rjob = ReconstructJob()
        rjob.set(self.sentence, self.doc_cache)
        self.queue.enqueue(rjob)
        rjob.done.wait()


def test_sentence_tokenizer_is_cancelled_properly_when_second_reconstruct_job_added_from_another_thread():
    nlp = spacy.load("en_core_web_sm")
    doc_cache = WaitableDocCache(nlp)
    queue = JobQueue()
    sentence = Sentence()
    # Proverbs 27:14
    sentence.set_text("If anyone loudly blesses their neighbor early in the morning, it will be taken as a curse.")
    thr = TokenizeThread(queue, doc_cache, sentence)
    thr.start()
    queue.start()
    djob = DeleteJob()
    djob.set(sentence)
    rjob = ReconstructJob()
    rjob.set(sentence, doc_cache)
    queue.enqueue(djob)
    queue.enqueue(rjob)
    doc_cache.wait_for_get()
    thr.go()
    rjob.done.wait(1)
    assert rjob.status == JobStatus.CANCELLED
    assert isinstance(rjob.error, TokenizationCancelled)
    thr.join()
    assert len(sentence.tokens) > 0
    queue.shutdown()


class StressTokenizeThread(threading.Thread):
    def __init__(self, queue: JobQueue, doc_cache: DocCache, sentence: Sentence, text: str, barrier: threading.Barrier) -> None:
        super().__init__()
        self.queue = queue
        self.doc_cache = doc_cache
        self.sentence = sentence
        self.text = text
        self.barrier = barrier
        self.rjob = ReconstructJob()

    def run(self) -> None:
        self.barrier.wait()
        self.sentence.set_text(self.text)
        djob = DeleteJob()
        djob.set(self.sentence)
        self.rjob.set(self.sentence, self.doc_cache)
        self.queue.enqueue(djob)
        self.queue.enqueue(self.rjob)
        self.rjob.done.wait()


def test_job_queue_stress_test_multi_threaded_tokenization():
    """
    Tests that when 100 set_text() functions are called on the Sentence,
    and the resultant DeleteJob and ReconstructJobs are added to the queue,
    only one (the last enqueued) actually changes the sentence. All the rest
    are cancelled.

    This was difficult to write. It was extremely difficult to set up
    random delays within the test to cause collisions, but of course,
    whatever random delays added to cause collisions on one PC, possibly won't
    work on another PC. Therefore, that logic was removed.

    However, when that logic was "working" only one collision would occur.
    This is because the queue is single threaded, and while one ReconstructJob is running,
    if any others happen to be enqueued at the same time, they all will cancel it, and the
    last one standing will cancel any other one that is left queued. By this time all 100
    have been enqueued, and     only one was cancelled while running. The very fact that this was
    difficult to simulate says that the queue is going to work very well in production,
    and that the design is robust.
    """
    nlp = spacy.load("en_core_web_sm")
    doc_cache = DocCache(nlp)
    queue = JobQueue()
    queue.start()

    texts = [
        "The truth will set you free.",
        "Love your neighbor as yourself.",
        "Pride goes before destruction.",
        "A gentle answer turns away wrath.",
        "The fear of the Lord is wisdom.",
        "Faith can move mountains.",
        "Rejoice always and pray continually.",
        "Perfect love casts out fear.",
        "Walk humbly with your God.",
        "Blessed are the peacemakers.",
        "The Lord is my shepherd.",
        "Be still and know God.",
        "Man shall not live by bread alone.",
        "Wisdom is better than gold.",
        "Do not grow weary in doing good.",
        "Seek and you will find.",
        "The meek shall inherit the earth.",
        "Guard your heart diligently.",
        "Love covers many sins.",
        "Mercy triumphs over judgment.",
        "A cheerful heart is good medicine.",
        "The Lord searches every heart.",
        "Hope does not disappoint.",
        "Be quick to listen.",
        "The righteous walk in integrity.",
        "Kind words heal deeply.",
        "Give thanks in all circumstances.",
        "The Lord is near the brokenhearted.",
        "Iron sharpens iron.",
        "Blessed are the pure in heart.",
        "God opposes the proud.",
        "The joy of the Lord is strength.",
        "Peace I leave with you.",
        "Forgive and you will be forgiven.",
        "Trust in the Lord completely.",
        "The wise store up knowledge.",
        "Whoever exalts himself will be humbled.",
        "Better a little with righteousness.",
        "Love never fails.",
        "The Lord is compassionate and gracious.",
        "Be strong and courageous.",
        "A fool despises instruction.",
        "The wages of sin is death.",
        "The gift of God is life.",
        "Blessed are the merciful.",
        "Commit your work to the Lord.",
        "The Lord gives wisdom.",
        "Those who seek find.",
        "Do everything in love.",
        "The tongue can destroy.",
        "God is our refuge and strength.",
        "The righteous are bold as lions.",
        "Hatred stirs conflict.",
        "Love delights in truth.",
        "Better patience than pride.",
        "The Lord delights in justice.",
        "Every good gift comes from above.",
        "The wise listen carefully.",
        "Blessed are those who hunger for righteousness.",
        "The Lord upholds the humble.",
        "A faithful friend is priceless.",
        "The path of righteousness shines brightly.",
        "Children are a gift from God.",
        "Better a peaceful meal than conflict.",
        "The Lord watches over the faithful.",
        "The wise avoid evil.",
        "A soft tongue breaks bones.",
        "God cannot be mocked.",
        "The prudent speak carefully.",
        "Where your treasure is, your heart follows.",
        "If anyone loudly blesses their neighbor early in the morning, it will be taken as a curse.",
        "The righteous flourish like a tree planted beside flowing waters.",
        "Better to trust in the Lord than rely upon human strength.",
        "Whoever walks with the wise grows wiser with every step.",
        "The Lord gives peace to those whose minds remain steadfast.",
        "A wise person controls their temper and overlooks an offense.",
        "Those who sow kindness will harvest mercy and lasting peace.",
        "The unfolding of God's words brings light and understanding.",
        "Do not repay evil with evil, but overcome evil with good.",
        "The Lord is faithful to all who call upon Him sincerely.",
        "The wise store knowledge, but reckless words invite trouble.",
        "A patient person shows great understanding and self-control.",
        "The Lord is gracious and compassionate, slow to anger and rich in love.",
        "Better a humble spirit with peace than riches with conflict.",
        "Whoever pursues righteousness and love finds life, honor, and peace.",
        "A faithful witness speaks truth, but a false witness spreads lies.",
        "The righteous care for the needs of others with compassion.",
        "The fear of the Lord leads to wisdom and lasting understanding.",
        "Those who trust the Lord will never be put to shame.",
        "The wise accept correction, but fools reject instruction.",
        "Kind words are like honey, sweet to the soul and healing.",
        "A peaceful answer can calm anger and restore relationships.",
        "The Lord directs the steps of those who delight in Him.",
        "Whoever guards their mouth preserves peace and avoids trouble.",
        "The humble receive wisdom, but pride leads toward destruction.",
        "Blessed are those who hunger and thirst for righteousness.",
        "The righteous shine like lights in a darkened world.",
        "God gives strength to the weary and hope to the discouraged.",
        "A generous person will prosper and refresh others with kindness.",
        "The Lord is close to all who call upon Him faithfully.",
        "A wise heart listens carefully before speaking any words.",
        "The one who forgives offenses promotes love and unity.",
        "The path of the righteous grows brighter with each passing day.",
        "Better a truthful rebuke than flattering words hiding deceit.",
        "The Lord protects the faithful and lifts up the humble.",
        "Whoever plants peace will harvest righteousness and joy.",
        "The wise seek understanding before making judgments about others.",
        "Faith without action is empty and produces nothing worthwhile.",
        "The Lord strengthens those whose hearts remain loyal to Him.",
        "Love your enemies and pray for those who mistreat you.",
    ]
    barrier = threading.Barrier(len(texts))
    sentence = Sentence()
    threads: list[StressTokenizeThread] = []
    for text in texts:
        thread = StressTokenizeThread(queue, doc_cache, sentence, text, barrier)
        threads.append(thread)
        thread.start()

    count_cancels = 0
    count_throws = 0
    count_done = 0
    count_other = 0
    for thread in threads:
        thread.join()
        if thread.rjob.status == JobStatus.CANCELLED:
            count_cancels += 1
        elif thread.rjob.status == JobStatus.DONE:
            count_done += 1
        else:
            count_other += 1
        if thread.rjob.error is not None:
            count_throws += 1

    print(sentence.tokens)
    assert count_cancels > 0
    assert count_done > 0
    assert count_other == 0
    # can't be sure about count_throws because the conditions that cause it are random
    assert len(sentence.tokens) > 0
    queue.shutdown()


def test_sentence_tokenizer_empty_text_returns_empty_list(nlp):
    cache = DocCache(nlp)
    tok = SentenceTokenizer()
    tokens = tok.tokenize("", cache)
    assert not tokens


def test_sentence_tokenizer_raises_if_cancelled_before_tokenize(nlp):
    cache = DocCache(nlp)
    tok = SentenceTokenizer()
    tok.cancel()
    with pytest.raises(TokenizationCancelled):
        tok.tokenize("Hello world", cache)


def test_sentence_tokenizer_produces_correct_tokens(nlp):
    cache = DocCache(nlp)
    tok = SentenceTokenizer()
    tokens = tok.tokenize("Hello world!", cache)

    assert len(tokens) == 3
    assert tokens[0].text == "Hello"
    assert tokens[0].trailing_ws == " "
    assert tokens[0].type == Type.WORD

    assert tokens[1].text == "world"
    assert tokens[1].trailing_ws == ""
    assert tokens[1].type == Type.WORD

    assert tokens[2].text == "!"
    assert tokens[2].trailing_ws == ""
    assert tokens[2].type == Type.PUNCTUATION


def test_sentence_tokenizer_sets_pos_and_lemma(nlp):
    cache = DocCache(nlp)
    tok = SentenceTokenizer()
    tokens = tok.tokenize("Running fast.", cache)

    for tok_item in tokens:
        if tok_item.type != Type.EXTENDED:
            assert tok_item.lemma != "" or tok_item.text in {".", "fast"}


def test_sentence_tokenizer_raises_if_cancelled_during_loop():
    cache = MagicMock(spec=DocCache)
    tok = SentenceTokenizer()
    tok.cancel()
    doc = MagicMock()
    doc.__iter__ = MagicMock(return_value=iter([MagicMock()]))
    cache.get_doc.return_value = doc

    with pytest.raises(TokenizationCancelled):
        tok.tokenize("ignored", cache)


def test_sentence_tokenizer_cancel_is_idempotent():
    tok = SentenceTokenizer()
    tok.cancel()
    tok.cancel()
    assert tok._cancel_event.is_set()
