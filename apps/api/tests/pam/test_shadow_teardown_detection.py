"""Faz 51 sonrası — `app/routes/pam_audit.py::_recording_ends_with_teardown`
için birim testleri. Gerçek bir üretim bug'ının düzeltmesi: guacd bir
RDP oturumu KAPANIRKEN kayda tam bir "her şeyi imha et" (`dispose`)
dizisi yazar, kök katmanın (`dispose,1.0`) imhasıyla biter — bunu
OLDUĞU GİBİ bir izleyiciye göndermek garantili bir siyah ekrana yol
açar (gerçek bir kayıt dosyasında canlı olarak GÖZLEMLENDİ)."""

from app.routes.pam_audit import _recording_ends_with_teardown


def test_detects_trailing_root_layer_dispose():
    text = "4.sync,7.8878158;7.dispose,2.-1;7.dispose,1.0;"
    assert _recording_ends_with_teardown(text) is True


def test_does_not_flag_normal_mid_session_content():
    text = "4.size,1.0,4.1280,3.800;4.sync,7.8878158;"
    assert _recording_ends_with_teardown(text) is False


def test_does_not_flag_dispose_of_a_non_root_buffer_layer():
    """Ekran ortasında geçici buffer katmanlarının (negatif indeksli)
    imha edilmesi TAMAMEN NORMAL bir RDP oturumu davranışı — yalnızca
    kök/varsayılan katmanın (`0`) imhası oturum sonunu işaret eder."""
    text = "4.sync,7.8878158;7.dispose,3.-25;"
    assert _recording_ends_with_teardown(text) is False


def test_empty_text_is_not_flagged():
    assert _recording_ends_with_teardown("") is False


def test_real_recorded_teardown_tail_is_detected():
    """Gerçek bir canlı kayıt dosyasının kuyruğundan (bkz. bu oturumda
    bulunan gerçek bug) birebir kopyalanmış bir örnek."""
    text = (
        "4.sync,7.8881423;7.dispose,2.-3;7.dispose,2.-4;7.dispose,2.-7;"
        "7.dispose,3.-25;7.dispose,3.-78;7.dispose,2.-1;7.dispose,1.0;"
    )
    assert _recording_ends_with_teardown(text) is True
