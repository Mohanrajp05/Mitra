// Shared, dependency-free validation rules for the authentication forms.
// These mirror the kind of guidance Google and other large sites show:
// a well-formed email address and a password that is long enough and mixes
// character types, without leading/trailing spaces.

export const EMAIL_MAX_LENGTH = 254
export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 64

// Deliberately strict enough to reject obvious mistakes but permissive about
// the characters people legitimately use in the local part of an address.
const EMAIL_PATTERN =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$/

export const PASSWORD_RULES = [
  {
    id: 'length',
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    test: (value) => value.length >= PASSWORD_MIN_LENGTH,
  },
  {
    id: 'uppercase',
    label: 'One uppercase letter (A-Z)',
    test: (value) => /[A-Z]/.test(value),
  },
  {
    id: 'lowercase',
    label: 'One lowercase letter (a-z)',
    test: (value) => /[a-z]/.test(value),
  },
  {
    id: 'number',
    label: 'One number (0-9)',
    test: (value) => /[0-9]/.test(value),
  },
  {
    id: 'special',
    label: 'One special character (!@#$%^&*)',
    test: (value) => /[^A-Za-z0-9\s]/.test(value),
  },
  {
    id: 'no-spaces',
    label: 'No spaces',
    test: (value) => !/\s/.test(value),
  },
]

const INVALID_EMAIL_MESSAGE =
  'Enter a valid email address, like name@example.com.'

export function validateEmail(rawValue) {
  const value = (rawValue || '').trim()

  if (!value) {
    return { valid: false, message: 'Enter your email address.' }
  }
  if (value.length > EMAIL_MAX_LENGTH) {
    return {
      valid: false,
      message: `Email address must be ${EMAIL_MAX_LENGTH} characters or fewer.`,
    }
  }
  if (/\s/.test(value)) {
    return { valid: false, message: 'Email address cannot contain spaces.' }
  }

  const parts = value.split('@')
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return {
      valid: false,
      message: 'Enter a valid email address with a single @ symbol.',
    }
  }

  const [local, domain] = parts
  if (local.length > 64) {
    return {
      valid: false,
      message: 'The part before @ must be 64 characters or fewer.',
    }
  }
  if (local.startsWith('.') || local.endsWith('.') || local.includes('..')) {
    return {
      valid: false,
      message: 'Email address cannot start, end, or contain consecutive dots.',
    }
  }
  if (!domain.includes('.')) {
    return {
      valid: false,
      message: 'The domain must include a dot, like example.com.',
    }
  }
  if (!EMAIL_PATTERN.test(value)) {
    return { valid: false, message: INVALID_EMAIL_MESSAGE }
  }

  return { valid: true, message: '' }
}

export function getPasswordChecks(rawValue) {
  const value = rawValue || ''
  return PASSWORD_RULES.map((rule) => ({
    ...rule,
    passed: rule.test(value),
  }))
}

export function validatePassword(rawValue) {
  const value = rawValue || ''

  if (!value) {
    return { valid: false, message: 'Create a password.' }
  }
  if (value.length > PASSWORD_MAX_LENGTH) {
    return {
      valid: false,
      message: `Password must be ${PASSWORD_MAX_LENGTH} characters or fewer.`,
    }
  }
  if (getPasswordChecks(value).some((rule) => !rule.passed)) {
    return {
      valid: false,
      message: 'Your password does not meet all the requirements yet.',
    }
  }

  return { valid: true, message: '' }
}

export function validateConfirmPassword(password, confirmPassword) {
  if (!confirmPassword) {
    return { valid: false, message: 'Re-enter your password to confirm it.' }
  }
  if (password !== confirmPassword) {
    return { valid: false, message: 'Passwords do not match.' }
  }
  return { valid: true, message: '' }
}

const STRENGTH_LEVELS = ['very-weak', 'weak', 'fair', 'good', 'strong']
const STRENGTH_LABELS = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong']

export function getPasswordStrength(rawValue) {
  const value = rawValue || ''

  if (!value) {
    return { score: 0, percent: 0, level: 'empty', label: '' }
  }

  const passedCount = getPasswordChecks(value).filter(
    (rule) => rule.passed,
  ).length

  let score = 0
  if (value.length >= PASSWORD_MIN_LENGTH) score += 1
  if (value.length >= 12) score += 1
  if (passedCount >= 5) score += 1
  if (passedCount === PASSWORD_RULES.length) score += 1
  score = Math.min(score, 4)

  return {
    score,
    percent: score === 0 ? 8 : score * 25,
    level: STRENGTH_LEVELS[score],
    label: STRENGTH_LABELS[score],
  }
}
