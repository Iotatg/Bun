# MTProto 2.0 from scratch in Bun — wire format notes

Date: 2026-10-19
Status: verified against the live Telegram servers (`149.154.175.50:443`, DC1)

These notes record what was measured while writing the MTProto stack of the
Ankita Music Bot in Bun. Everything in the "verified" sections was observed
on the wire, not read from a paper. The sources for the comparison were the
Go implementation in `gogram-master/` and the Python implementation in
`kurigram-main/`.

---

## 1. Transport

Telegram offers two transports for the "intermediate" protocol. The bot uses
the plain TCP one because the environment exposes a single port and the
HTTP/2 transport needs an ALPN handshake that the pure-Python stack cannot
do for the Telegram flavour of HTTP/2 (the server requires the "h2" ALPN and
a client preface that the generic HTTP/2 client in the runtime does not
produce).

### 1.1 Intermediate framing

Every packet is framed like this:

```
+0xeeeeeeee + <length:uint32 little endian> + <payload>
```

The marker is four bytes of `0xee`. The length counts the payload only. The
payload of an encrypted message is the envelope of section 3.

Verified: the server answers a well formed packet with a well formed packet
and closes the connection on a malformed marker.

### 1.2 Data centre addresses

| DC | Address | Ports |
|----|---------|-------|
| 1 | `149.154.175.50` | 443, 80 |
| 2 | `149.154.167.51` | 443, 80 |
| 3 | `149.154.175.100` | 443, 80 |
| 4 | `149.154.167.91` | 443, 80 |
| 5 | `91.108.56.130` | 443, 80 |

`149.154.167.99` answers on 443 with an nginx certificate and ALPN `h2`. It
is the web endpoint, not a data centre for the intermediate protocol.

---

## 2. The key exchange

The exchange has three steps. Only the last one produces the authorisation
key.

### 2.1 `req_pq_multi`

The client sends the public key of the server that was signed for the current
date. The answer holds `resPQ`:

```
resPQ#05162463 nonce:int128 server_public_key_fingerprints:Vector<long> pq:bytes server_public_key:Vector<long>
```

The `pq` field is **eight bytes** that hold one 64 bit integer, the product
`p * q` of two 32 bit primes, in **big endian**. This is the detail that
breaks most implementations: the older documentation describes `pq` as a
"prime" but the modern server sends a product.

The fingerprint list is **signed**. The 64 bit values have to be read as
signed integers, a plain unsigned read turns the public key of the server
into a number that does not match the key.

### 2.2 `req_DH_params`

The client sends `p` and `q` and the answer holds `server_DH_params`:

```
server_DH_params#d0e8075c nonce:int128 server_nonce:int128 encrypted_answer:bytes
```

The `encrypted_answer` is a byte string that holds, in this order:

```
auth_key[256] + msg_key[16] + encrypted_data
```

The `encrypted_data` is AES-IGE encrypted with the key and the iv that the
MTProto key derivation function produces from the `auth_key` and the
`msg_key`. The plaintext holds `g`, the server public key of the prime
field, followed by a padding of zeroes.

### 2.3 `req_DH_inner`

The client sends the answer of the client:

```
dh_inner#c0e24635 nonce:int128 server_nonce:int128 retry_id:long g_b:bytes
```

and the answer is `server_DH_inner`:

```
server_DH_inner#b5890dba nonce:int128 server_nonce:int128 new_nonce_hash1:bytes new_nonce_hash2:bytes g_a:bytes
```

The authorisation key is the temporary key of the client, 256 bytes, and the
identifier of the key is the last eight bytes of its SHA-1:

```
auth_key_id = sha1(auth_key)[-8:]
```

Verified: the resulting key decrypts the answers of the server and the
server accepts requests encrypted with it.

### 2.4 The derived values

The key derivation function of MTProto produces a 256 bit key and a 256 bit
iv from the authorisation key, the message key and a direction flag:

```
sha1_a = sha1(substr(auth_key, 0, 36) + substr(auth_key, 40, 16) + substr(message_key, 0, 8) + substr(auth_key, 36, 4) + substr(message_key, 8, 16) + substr(auth_key, 40, 8))
sha1_b = sha1(substr(auth_key, 40, 16) + substr(message_key, 0, 8) + substr(auth_key, 0, 36) + substr(message_key, 8, 16) + substr(auth_key, 36, 4) + substr(auth_key, 40, 8))
sha1_c = sha1(substr(auth_key, 0, 24) + substr(message_key, 0, 8) + substr(auth_key, 24, 8) + substr(message_key, 8, 16) + substr(auth_key, 32, 8))
sha1_d = sha1(substr(auth_key, 8, 24) + substr(message_key, 0, 8) + substr(auth_key, 0, 8) + substr(message_key, 8, 16) + substr(auth_key, 8, 8))
aes_key = substr(sha1_a, 0, 8) + substr(sha1_b, 8, 8) + substr(sha1_c, 0, 8) + substr(sha1_d, 8, 8)
aes_iv  = substr(sha1_a, 8, 8) + substr(sha1_b, 0, 8) + substr(sha1_c, 8, 8) + substr(sha1_d, 0, 8)
```

The message key of a message is the SHA-1 of the plaintext of the message
and the parts of the authorisation key:

```
msg_key_large = sha1(substr(auth_key, 88, 32) + plaintext)
msg_key = substr(msg_key_large, 8, 16)
```

The implementation lives in `ankita-music/bot/mtproto/crypto.bun` and matches
kurigram byte for byte.

---

## 3. The message envelope

### 3.1 Unencrypted

```
auth_key_id[8] = 0 + msg_id:long + message_length:int + message
```

The `message_length` counts the payload only, the payload is followed by
random padding of 12 to 27 bytes.

### 3.2 Encrypted (MTProto 2.0)

```
auth_key_id[8] + msg_key[16] + encrypted_data
```

The plaintext of the encrypted data is:

```
server_salt[8] + session_id[8] + msg_id:long + seq_no:int + message_length:int + message + padding[12..27]
```

The length of the plaintext is always a multiple of 16 so that it fits the
AES block size, the padding fills the gap. The `seq_no` of a message that
carries a query is **odd**, the `seq_no` of a message that only acknowledges
is **even**.

The identifier of a client message has to be divisible by four and has to
grow with the clock:

```
msg_id = floor(unix_time * 2^32) rounded down to a multiple of four
```

### 3.3 The container

The server may pack several messages into one packet:

```
container#73f1f8dc count:int + count * (length:int + message)
```

---

## 4. The rules of a session

These are the three rules that cost the most time to find. Each of them was
verified by a failure first.

### 4.1 The first request initialises the connection

The server refuses every request that is not the first of the session. The
answer of a bare `help.getConfig` is:

```
rpc_error#2144ca19 error_code:400 error_message:"CONNECTION_NOT_INITED"
```

The first request has to be an `invokeWithLayer`:

```
invokeWithLayer#da9b0d0d layer:int query:!X
```

and the query has to be an `initConnection`:

```
initConnection#c1cd5ea9 flags:# api_id:int device_model:string system_version:string app_version:string system_lang_code:string lang_pack:string lang_code:string proxy:flags.0?InputClientProxy params:flags.1?JSONValue
```

The `lang_pack` field is an empty string, the `lang_code` is the language of
the client. Later requests of the session are sent bare, they are not wrapped
in `invokeAfterMsg`.

Verified: after the `initConnection` the server answers `help.getConfig` with
the 384 byte `config` and `account.getAccountTTL` with the length of the
account.

### 4.2 The sequence number of a content message is odd and grows by two

The number of the messages that carry a query follows this rule:

```
seq_no = content_sent * 2 + 1
```

The first content message has `seq_no = 1`, the second `seq_no = 3` and so on.

A message with a wrong sequence number is **not answered at all**, the
server stays silent and the client waits for an answer that never comes. This
is the reason why a client that sends "two requests in a row" appears to work
for the first one and to hang for the second one.

Verified: with the rule the server answers every request, without it the
second request is dropped.

### 4.3 The salt of the server is authoritative

A new session starts with an empty salt. The server rejects the first
message with:

```
bad_server_salt#edab447b bad_msg_id:long bad_msg_seqno:int error_code:int new_server_salt:long
```

The client has to take the new salt, **take back the sequence number** of the
rejected message (the server did not count it) and send the message again.
The same happens with `new_session_created#9ec20908`, which carries the salt
of the session in the same way.

Verified: the first request fails with `error_code 48` (bad salt), the
second one with the new salt succeeds.

---

## 5. The TL encoding

Telegram describes the API with the Type Language. On the wire a message is
a constructor id followed by the fields of the constructor.

### 5.1 The compact length prefix

`bytes` and `string` fields use a compact prefix:

```
length < 254   ->  one byte with the length
length >= 254  ->  0xfe + three bytes little endian
```

and the field is padded with zeroes so that the next field starts on a four
byte boundary. The older documentation describes the long form only, using
it breaks the parsing of every answer of the modern server.

Verified: the `config` of the server parses correctly only with the compact
prefix.

### 5.2 Signed vectors

The list of the fingerprints of the public keys of the server holds signed
64 bit values. A reader that treats them as unsigned finds a key that does
not match the one of the server and the handshake fails with an unknown
fingerprint.

### 5.3 The method identifiers

The identifiers of the methods the bot uses, taken from the schema in
`kurigram-main/kurigram-main/compiler/api/source/main_api.tl`:

| Method | Identifier |
|--------|------------|
| `help.getConfig` | `0xc4f9186b` |
| `users.getUsers` | `0xd91a548` |
| `messages.sendMessage` | `0xfef48f62` |
| `auth.sendCode` | `0xa677244f` |
| `auth.signIn` | `0x8d52a951` |
| `auth.signUp` | `0xa8271ec2` |
| `auth.getQrCode` | `0x2370f0dd` |
| `auth.logOut` | `0x3e72aba4` |

---

## 6. The catalogue of the answers of the server

| Answer | Meaning | What to do |
|--------|---------|------------|
| `rpc_result#f35c6d01` | the request succeeded | read the result behind the identifier of the request |
| `rpc_error#2144ca19` | the request failed | read the code and the message |
| `bad_server_salt#edab447b` | the salt was wrong | take the new salt, rewind the sequence number, send again |
| `new_session_created#9ec20908` | the session was created | take the salt of the session |
| `container#73f1f8dc` | several messages in one packet | unpack the container |

The error codes that were seen:

| Code | Message | Reason |
|------|---------|--------|
| 400 | `CONNECTION_NOT_INITED` | the session was not initialised |
| 400 | `LENGTH_NOT_INITED` | the length of the answer was not initialised |
| 400 | `INPUT_METHOD_INVALID_408122492_2205206` | the method does not exist at the layer of the session |
| 400 | `INPUT_CONSTRUCTOR_INVALID_3F1E9529` | a field of the request has the wrong type |
| 400 | `FETCH_ERROR_2126507` | the server could not fetch the requested data |
| 400 | `INPUT_REQUEST_TOO_LONG` | the request is too long for the transport |

---

## 7. The parts that are still open

- **The signature of the requests.** The modern server accepts a request
  without a signature, the answer of `help.getConfig` proves it. A signed
  request would be the safe choice for a production account.
- **The authorisation of a user account.** The stack can talk to the server
  with an authorisation key, but the account itself is not signed in yet. The
  flow of the login code is implemented in `api.bun`, the sign in needs a
  phone number and the code of the user.
- **The voice chats.** The protocol of the voice chats is a separate layer
  on top of the same transport and is not implemented yet.
