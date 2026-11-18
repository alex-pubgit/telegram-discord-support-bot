# Bundled data

## `bip39_english.txt`

The BIP-39 English wordlist: 2048 lowercase words, one per line. The bot uses it only to
recognize a wallet recovery phrase that a member pasted into a chat, so the message can be removed.
It never generates, stores or derives keys.

- Source: <https://github.com/bitcoin/bips/blob/ce1862ac6bcffa1dd20aad858380e51e66e949ea/bip-0039/english.txt>
  (the `bitcoin/bips` repository, file `bip-0039/english.txt`), retrieved on 2026-11-17.
- License: MIT. The Copyright section of
  [BIP-39](https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki) states that the BIP,
  which this wordlist is part of, falls under the MIT License.
- The file is unmodified. Its SHA-256 is
  `2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda`, and a test checks the bundled
  copy against that value and against the word count.
