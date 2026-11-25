<?php

namespace Drupal\restyl_site\Form;

use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;

/**
 * Collects enquiries without storing their personal data in Drupal.
 */
final class ContactForm extends FormBase {

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'restyl_site_contact';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state, $division = NULL) {
    $division = $division === 'energy' ? 'energy' : 'elektro';
    $form['division'] = ['#type' => 'value', '#value' => $division];
    $form['intro'] = [
      '#markup' => '<p>' . $this->t('Zájem z formuláře: @division', ['@division' => strtoupper($division)]) . '</p>',
    ];
    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Jméno a příjmení'),
      '#required' => TRUE,
      '#maxlength' => 150,
    ];
    $form['email'] = [
      '#type' => 'email',
      '#title' => $this->t('E-mail'),
      '#required' => TRUE,
      '#maxlength' => 254,
    ];
    $form['phone'] = [
      '#type' => 'tel',
      '#title' => $this->t('Mobilní telefon'),
      '#maxlength' => 60,
    ];
    $form['company'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Firma'),
      '#maxlength' => 150,
    ];
    $form['address'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Adresa'),
      '#rows' => 2,
      '#maxlength' => 500,
    ];
    $options = $division === 'elektro' ? [
      'vn' => $this->t('VN, trafostanice stožárové a zemní'),
      'nn' => $this->t('NN elektroinstalace'),
      'hromosvody' => $this->t('Hromosvody klasické i aktivní'),
      'servis' => $this->t('Servis, revize a opravy'),
      'zdroje' => $this->t('Náhradní zdroje'),
      'mereni' => $this->t('Měření odběrů, oteplení a optimalizace'),
    ] : [
      'tepelne_cerpadlo' => $this->t('Tepelné čerpadlo (či kombinace TČ a FVE)'),
      'automatizace' => $this->t('Domácí a průmyslovou automatizaci'),
      'rekuperace' => $this->t('Rekuperaci a větrání'),
      'ohrev' => $this->t('Ohřev TUV'),
      'panely' => $this->t('FV panely a komponenty'),
      'elektrarna' => $this->t('Solární elektrárnu na klíč'),
      'baterie' => $this->t('Baterie ke stávající elektrárně (hybridní systém)'),
      'osvetleni' => $this->t('Osvětlení a inteligentní elektroinstalaci'),
      'audit' => $this->t('Audit, revizi či servis'),
    ];
    $form['services'] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('O jaké služby máte zájem?'),
      '#description' => $this->t('Zaškrtněte jednu nebo více možností.'),
      '#options' => $options,
      '#required' => TRUE,
    ];
    $form['message'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Vaše zpráva'),
      '#maxlength' => 10000,
    ];
    $privacy_url = $division === 'elektro'
      ? 'https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2018/08/GDPR_RESTYL_ELEKTRO.pdf?v=3c66ef14'
      : 'https://media.smtx.cz/file/media-b8a28-eu/s/768186e0fbc6/2018/08/GDPR_RESTYL_ENERGY.pdf?v=6baa234b';
    $form['consent'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Souhlasím se <a href=":url">zpracováním osobních údajů</a>', [':url' => $privacy_url]),
      '#required' => TRUE,
    ];
    $form['actions'] = ['#type' => 'actions'];
    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Odeslat'),
    ];
    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    parent::validateForm($form, $form_state);
    if (!\Drupal::service('flood')->isAllowed('restyl_site.contact', 5, 3600)) {
      $form_state->setErrorByName('actions', $this->t('Byl překročen limit odeslání. Zkuste to prosím později.'));
    }
    $division = $form_state->getValue('division');
    $recipient = getenv('RESTYL_MAIL_TO_' . strtoupper($division)) ?: '';
    $sender = getenv('RESTYL_MAIL_FROM') ?: '';
    $validator = \Drupal::service('email.validator');
    if (!$validator->isValid($recipient) || !$validator->isValid($sender)) {
      $form_state->setErrorByName('actions', $this->t('Formulář není správně nastaven. Kontaktujte nás prosím jiným způsobem.'));
      \Drupal::logger('restyl_site')->error('Contact form mail addresses are not configured or are invalid.');
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    \Drupal::service('flood')->register('restyl_site.contact', 3600);
    $division = $form_state->getValue('division');
    $services = [];
    foreach (array_filter($form_state->getValue('services')) as $key) {
      $services[] = (string) $form['services']['#options'][$key];
    }
    $body = implode("\n", [
      'Jméno: ' . $form_state->getValue('name'),
      'E-mail: ' . $form_state->getValue('email'),
      'Telefon: ' . $form_state->getValue('phone'),
      'Firma: ' . $form_state->getValue('company'),
      'Adresa: ' . $form_state->getValue('address'),
      'Služby: ' . implode(', ', $services),
      'Zpráva: ' . $form_state->getValue('message'),
      'Souhlas se zpracováním osobních údajů: ano',
    ]);
    $params = [
      'subject' => 'Poptávka RESTYL ' . strtoupper($division),
      'body' => $body,
      'from' => getenv('RESTYL_MAIL_FROM'),
      'reply_to' => $form_state->getValue('email'),
    ];
    try {
      $result = \Drupal::service('plugin.manager.mail')->mail(
        'restyl_site',
        'contact',
        getenv('RESTYL_MAIL_TO_' . strtoupper($division)),
        \Drupal::languageManager()->getDefaultLanguage()->getId(),
        $params,
        $form_state->getValue('email'),
      );
    }
    catch (\Symfony\Component\Mailer\Exception\TransportExceptionInterface $e) {
      $result = ['result' => FALSE];
    }
    if (empty($result['result'])) {
      \Drupal::logger('restyl_site')->error('Contact form email could not be sent. Check the mail transport configuration.');
      $this->messenger()->addError($this->t('Zprávu se nepodařilo odeslat. Zkuste to později nebo nás kontaktujte jiným způsobem.'));
      $form_state->setRebuild();
      return;
    }
    $this->messenger()->addStatus($this->t('Děkujeme, vaše zpráva byla odeslána.'));
    $form_state->setRedirect('<front>');
  }

}
